# -*- coding: utf-8 -*-
"""离线测试用的 pydantic 极简替身。

只实现本案例用到的能力：``BaseModel`` / ``ConfigDict`` / ``Field`` / ``ValidationError``
以及 ``model_validate`` 与 ``model_json_schema``。生产环境永远使用真正的 pydantic，
本文件仅在被测试通过 ``sys.modules`` 注入时生效。
"""
from __future__ import annotations

_MISSING = object()


class ConfigDict(dict):
    pass


class FieldInfo:
    def __init__(self, default=_MISSING, *, min_length=None, max_length=None,
                 title=None, description=None) -> None:
        self.default = default
        self.min_length = min_length
        self.max_length = max_length
        self.title = title
        self.description = description


def Field(default=_MISSING, **kwargs) -> FieldInfo:  # noqa: N802 - 对齐 pydantic 命名
    return FieldInfo(default, **kwargs)


def model_validator(*, mode: str = "after"):
    """极简 model_validator：只支持 mode="after"（对象构建后校验）。"""

    def decorator(func):
        func.__pydantic_after_validator__ = True
        return func

    return decorator


_SIMPLE_TYPES = {
    "str": str, "int": int, "bool": bool, "float": float,
    "str | None": (str, type(None)), "int | None": (int, type(None)),
}


def _resolve(typ):
    """把 ``from __future__ import annotations`` 产生的字符串注解还原成类型。"""
    if isinstance(typ, str):
        name = typ.strip().strip('"').strip("'")
        return _SIMPLE_TYPES.get(name, object)
    return typ


class ValidationError(ValueError):
    def __init__(self, errors: list[dict]) -> None:
        super().__init__("validation failed")
        self._errors = errors

    def errors(self, include_context: bool = True, include_url: bool = True) -> list[dict]:
        return [
            {k: v for k, v in err.items()
             if k not in ("ctx", "url") or (include_context and k == "ctx") or (include_url and k == "url")}
            for err in self._errors
        ]


def _type_name(typ) -> str:
    return {str: "string", int: "integer", bool: "boolean", float: "number"}.get(typ, "object")


class BaseModel:
    model_config: ConfigDict = ConfigDict()
    __fields__: dict[str, tuple] = {}

    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        fields: dict[str, tuple] = {}
        for name, typ in getattr(cls, "__annotations__", {}).items():
            if name == "model_config":
                continue
            info = cls.__dict__.get(name, _MISSING)
            fields[name] = (_resolve(typ), info)
        cls.__fields__ = fields

    @classmethod
    def model_validate(cls, data):
        if not isinstance(data, dict):
            raise ValidationError([{"type": "dict_type", "loc": (), "msg": "输入必须是对象"}])
        allowed = set(cls.__fields__)
        errors: list[dict] = []
        if cls.model_config.get("extra") == "forbid":
            for key in set(data) - allowed:
                errors.append({"type": "extra_forbidden", "loc": (key,), "msg": "不允许的字段"})

        values: dict[str, object] = {}
        for name, (typ, info) in cls.__fields__.items():
            if name in data:
                value = data[name]
            elif isinstance(info, FieldInfo) and info.default is not _MISSING:
                values[name] = info.default
                continue
            else:
                errors.append({"type": "missing", "loc": (name,), "msg": "缺少必填字段"})
                continue

            if typ is bool and not isinstance(value, bool):
                errors.append({"type": "bool_type", "loc": (name,), "msg": "需要布尔值"})
                continue
            if typ is str:
                if not isinstance(value, str):
                    errors.append({"type": "string_type", "loc": (name,), "msg": "需要字符串"})
                    continue
                if isinstance(info, FieldInfo):
                    if info.min_length is not None and len(value) < info.min_length:
                        errors.append({"type": "string_too_short", "loc": (name,), "msg": "字符串过短"})
                        continue
                    if info.max_length is not None and len(value) > info.max_length:
                        errors.append({"type": "string_too_long", "loc": (name,), "msg": "字符串过长"})
                        continue
            values[name] = value

        if errors:
            raise ValidationError(errors)
        obj = cls.__new__(cls)
        object.__setattr__(obj, "__dict__", values)

        # 执行 @model_validator(mode="after") 标记的校验方法
        for attr_name, attr in vars(cls).items():
            if not getattr(attr, "__pydantic_after_validator__", False):
                continue
            try:
                getattr(obj, attr_name)()
            except ValueError as exc:
                raise ValidationError([{
                    "type": "value_error",
                    "loc": (attr_name,),
                    "msg": str(exc),
                }]) from exc
        return obj

    @classmethod
    def model_json_schema(cls) -> dict:
        properties: dict[str, dict] = {}
        required: list[str] = []
        for name, (typ, info) in cls.__fields__.items():
            prop = {"type": _type_name(typ), "title": name}
            default = _MISSING
            if isinstance(info, FieldInfo):
                if info.title:
                    prop["title"] = info.title
                if info.description:
                    prop["description"] = info.description
                if info.min_length is not None:
                    prop["minLength"] = info.min_length
                if info.max_length is not None:
                    prop["maxLength"] = info.max_length
                default = info.default
            if default is _MISSING:
                required.append(name)
            else:
                prop["default"] = default
            properties[name] = prop
        schema = {
            "title": cls.__name__,
            "type": "object",
            "properties": properties,
            "required": required,
        }
        if cls.model_config.get("extra") == "forbid":
            schema["additionalProperties"] = False
        return schema
