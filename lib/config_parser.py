import os
from configobj import ConfigObj,flatten_errors
from configobj.validate import Validator
import logging
import re
import json
from jsonschema import Draft4Validator, validators

def _sub_env(section, key, env_opt=None, logger=None):
    logger = logger or logging.getLogger(__name__)

    def lookup(match):

        key = match.group(2)

        if key in env_opt.keys():
            return env_opt[key]

        return match.group(1)

    pattern = re.compile(r'(\${(.*)}s)')

    if type(section[key]) == list:
        for index, opt in enumerate(section[key]):
            replaced = pattern.sub(lookup, opt)
            if replaced is not None:
                section[key][index] = replaced
    else:
        replaced = pattern.sub(lookup, section[key])
        if replaced is not None:
            section[key] = replaced

class ConfigParse(object):

    def _config_check(self, cfg):
        if not os.path.exists(cfg):
            raise IOError("File %s does not exists" % cfg)

        return True

    def _configobj_init(self, cfg, cfg_spec, usr_cfg, os_env, opt_env):

        def _validate(self, obj):

            validator = Validator()
            results = obj.validate(validator)
            self.logger.info(results)
            if results != True:
                for (section_list, key, _) in flatten_errors(obj, results):
                    if key is not None:
                        raise Exception(
                            'The "%s" key in the section "%s" failed validation' % (key, ', '.join(section_list)))
                    else:
                        raise Exception('The following section was missing:%s ' % ', '.join(section_list))

        cfgobj = ConfigObj(cfg)

        if opt_env is not None:
            cfgobj.walk(_sub_env, env_opt=opt_env, logger=logger)

        if os_env is True:
            cfgobj.walk(_sub_env, env_opt=os.environ, logger=logger)

        if os.path.exists(usr_cfg):
            cfgobj.merge(usr_cfg)

        self.cfg = ConfigObj(cfgobj, configspec=cfg_spec)

        _validate(self, self.cfg)

    def _json_init(self, cfg, cfg_spec, usr_cfg, os_env, opt_env):

        def extend_with_default(validator_class):
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

        DefaultValidatingDraft4Validator = extend_with_default(Draft4Validator)

        temp_data = ''

        with open(cfg_spec, 'r') as f:
            temp_data = f.read()

        self.logger.info(json.dumps(temp_data, indent=4, sort_keys=True))

        json_schema = json.loads(temp_data)

        with open(cfg, 'r') as f:
            temp_data = f.read()

        json_data = json.loads(temp_data)

        DefaultValidatingDraft4Validator(json_schema).validate(json_data)

        self.cfg = json_data

    def __init__(self, cfg,  cfg_spec, usr_cfg='', cfg_type='configobj', os_env=False, opt_env=None, logger=None):
        self.logger = logger or logging.getLogger(__name__)

        self.supported_cfgs = ['json', 'configobj', 'configparse']

        self.logger.debug("cfg = %s" % cfg)
        self.logger.debug("cfg_spec = %s" % cfg_spec)
        self.logger.debug("usr_cfg = %s" % usr_cfg)

        self._config_check(cfg)
        self._config_check(cfg_spec)

        if cfg_type == "configobj":
            self._configobj_init(cfg, cfg_spec, usr_cfg, os_env, opt_env)
        elif cfg_type == "json":
            self._json_init(cfg, cfg_spec, usr_cfg, os_env, opt_env)


    def get_cfg(self):
        return self.cfg
