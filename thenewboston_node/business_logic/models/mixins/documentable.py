import json
import textwrap
import typing
from datetime import date, datetime
from inspect import getdoc, isclass

import class_doc

from thenewboston_node.core.utils.constants import SENTINEL
from thenewboston_node.core.utils.misc import humanize_camel_case, humanize_snake_case
from thenewboston_node.core.utils.types import hexstr

from .base import BaseMixin

TYPE_NAME_MAP = {
    str: 'string',
    hexstr: 'hexstr',
    int: 'integer',
    dict: 'object',
    list: 'array',
    tuple: 'array',
    datetime: 'datetime',
    typing.Any: 'any type',
}


def extract_attribute_docs(model):
    docs = {}
    for class_ in reversed(model.mro()):
        if class_ is not object:
            docs |= class_doc.extract_docs_from_cls_obj(cls=class_)

    return docs


def normalize_type_representation(type_, jsonify=True, targetized_types=(hexstr, datetime)):
    type_name = (TYPE_NAME_MAP.get(type_) or type_.__name__) if jsonify else type_.__name__
    if isclass(type_) and issubclass(type_, targetized_types + (DocumentableMixin,)):
        type_name = f'`{type_name}`_'

    return type_name


def default_serialize(obj):
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()


class DocumentableMixin(BaseMixin):
    attribute_docs = None

    @classmethod
    def get_nested_models(cls, known_models=(), include_self=False):
        assert cls not in known_models
        known_models = known_models or []
        if include_self:
            known_models.append(cls)

        for field_name in cls.get_field_names():
            field_type = cls.get_field_type(field_name)
            if issubclass(field_type, DocumentableMixin) and field_type not in known_models:
                known_models = field_type.get_nested_models(known_models, include_self=True)
            else:
                origin = typing.get_origin(field_type)
                if origin and issubclass(origin, list):
                    (item_type,) = typing.get_args(field_type)
                    if issubclass(item_type, DocumentableMixin) and item_type not in known_models:
                        known_models = item_type.get_nested_models(known_models, include_self=True)
                elif origin and issubclass(origin, dict):
                    item_key_type, item_value_type = typing.get_args(field_type)
                    if (
                        isclass(item_key_type) and issubclass(item_key_type, DocumentableMixin) and
                        item_key_type not in known_models
                    ):
                        known_models = item_key_type.get_nested_models(known_models, include_self=True)
                    if (
                        isclass(item_value_type) and issubclass(item_value_type, DocumentableMixin) and
                        item_value_type not in known_models
                    ):
                        known_models = item_value_type.get_nested_models(known_models, include_self=True)

        return known_models

    @classmethod
    def get_docstring(cls, use_humanized_default=True):
        doc = getdoc(cls)
        if doc is None and use_humanized_default:
            doc = humanize_camel_case(cls.__name__)

        return doc

    @classmethod
    def get_field_docstring(cls, field_name, imply_field_name=True):
        if (attribute_docs := cls.attribute_docs) is None:
            cls.attribute_docs = attribute_docs = extract_attribute_docs(cls)

        docstrings = attribute_docs.get(field_name)
        if docstrings:
            return textwrap.dedent(' '.join(docstrings))
        elif imply_field_name:
            return humanize_snake_case(field_name)

        return None

    @classmethod
    def get_field_type_representation(cls, field_name, jsonify=True):
        field_type = cls.get_field_type(field_name)

        origin = typing.get_origin(field_type)
        if origin:
            if issubclass(origin, list):
                (item_type,) = typing.get_args(field_type)
                return (
                    f'{normalize_type_representation(list, jsonify=jsonify)}'
                    f'[{normalize_type_representation(item_type, jsonify=jsonify)}]'
                )
            elif issubclass(origin, dict):
                item_key_type, item_value_type = typing.get_args(field_type)
                return (
                    f'{normalize_type_representation(dict, jsonify=jsonify)}'
                    f'[{normalize_type_representation(item_key_type, jsonify=jsonify)}, '
                    f'{normalize_type_representation(item_value_type, jsonify=jsonify)}]'
                )

        return normalize_type_representation(field_type, jsonify=jsonify)

    @classmethod
    def get_field_example_value(cls, field_name, jsonify=True):
        # We use `SENTINEL` here because theoretically `None` can be an example value (although it is unlikely)
        value = cls.get_field_metadata(field_name).get('example_value', SENTINEL)
        if value is SENTINEL:
            return None

        if jsonify:
            value = json.dumps(value, default=default_serialize)

        return value

    @classmethod
    def is_serialized_optional_field(cls, field_name):
        """
        Some fields are optional for internal construction dataclass instance, but they are mandatory when serialized.
        We need to reflect this in documentation.
        """
        # TODO(dmu) LOW: Consider using this method for validation
        value = cls.get_field_metadata(field_name).get('is_serialized_optional')
        return cls.is_optional_field(field_name) if value is None else value
