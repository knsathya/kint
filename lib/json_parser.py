import os
import json
import logging
from jsonschema import Draft4Validator, validators

class JSONParser(object):

    def _assert_exists(self, file):
        if not os.path.exists(file):
            raise IOError("File %s does not exists" % file)

        return True

    def _extend_with_default(self, validator_class):
        validate_properties = validator_class.VALIDATORS["properties"]

        def set_defaults(validator, properties, instance, schema):
            for property, subschema in properties.iteritems():
                if "default" in subschema:
                    instance.setdefault(property, subschema["default"])

            for error in validate_properties(
                    validator, properties, instance, schema,
            ):
                yield error

        return validators.extend(
            validator_class, {"properties": set_defaults},
        )

    def __init__(self, cfg,  schema, os_env=False, logger=None):
        self.logger = logger or logging.getLogger(__name__)

        self.logger.debug("cfg = %s" % cfg)
        self.logger.debug("cfg_schema = %s" % schema)

        self._assert_exists(cfg)
        self._assert_exists(schema)

        DefaultValidatingDraft4Validator = self._extend_with_default(Draft4Validator)

        temp_data = ''

        with open(schema, 'r') as f:
            temp_data = f.read()

        json_schema = json.loads(temp_data)

        with open(cfg, 'r') as f:
            temp_data = f.read()

        json_data = json.loads(temp_data)

        DefaultValidatingDraft4Validator(json_schema).validate(json_data)

        self.cfg = json_data

    def get_cfg(self):
        return self.cfg

    def print_cfg(self):
        self.logger.debug(json.dumps(self.cfg, indent=4, sort_keys=True))


if __name__ == "__main__":
    # Example usage:
    obj = {}
    schema = {'properties': {'foo': {'default': 'bar'}}}
    # Note jsonschem.validate(obj, schema, cls=DefaultValidatingDraft4Validator)
    # will not work because the metaschema contains `default` directives.
    #DefaultValidatingDraft4Validator(schema).validate(obj)
