import json
import os
import re
from jsonschema import validators, validate, Draft4Validator
from jsonmerge import merge
import logging
import io

# Make it work for Python 2+3 and with Unicode
try:
    to_unicode = unicode
except NameError:
    to_unicode = str

def flatten_dict(d):
    def expand(key, value):
        if isinstance(value, dict):
            return [ (key + '.' + k, v) for k, v in flatten_dict(value).items() ]
        else:
            return [ (key, value) ]

    items = [ item for k, v in d.items() for item in expand(k, v) ]

    return dict(items)

class JSONParser(object):

    def _extend_with_default(self, validator_class):
        validate_properties = validator_class.VALIDATORS["properties"]

        def set_defaults(validator, properties, instance, schema):
            for property_, subschema in properties.items():
                if "default" in subschema and not isinstance(instance, list):
                    instance.setdefault(property_, subschema["default"])

            for error in validate_properties(
                    validator, properties, instance, schema,
            ):
                yield error

        return validators.extend(
            validator_class, {"properties": set_defaults},
        )

    def _sub_env(self, data={}, env_opt={}):

        if not data or not env_opt:
            return data

        def lookup(match):
            key = match.group(2)

            print match.groups()

            if key in env_opt.keys():
                return env_opt[key]

            return match.group(1)

        pattern = re.compile(r'(\${(.*)})')

        if type(data) is dict:
            for key, value in data.iteritems():
                data[key] = self._sub_env(value, env_opt)
        elif type(data) is list or type(data) is type:
            for index, value in enumerate(data):
                data[index] = self._sub_env(value, env_opt)
        elif type(data) is str or type(data) is unicode:
            replaced = pattern.sub(lookup, data)
            if replaced is not None:
                return replaced
            else:
                return data

        return data

    def _sub_include(self, in_file, data, base_dir):

        if not data:
            return data

        def lookup(match):

            if len(match.groups()) > 1:
                print match.groups(), base_dir
                new_inc_file = os.path.abspath(os.path.join(base_dir, match.group(2)))
                if new_inc_file == os.path.abspath(in_file):
                    self.logger.warn("Warning: Circular dependency detected %s included in %s",
                                     new_inc_file, os.path.abspath(in_file))
                else:
                    new_data, new_status = self._get_json_data(new_inc_file, True, base_dir, True)
                    if new_status is True:
                        return new_data
                    else:
                        self.logger.warn("Not found valid data in %s", new_inc_file)

            return match.group(1)

        pattern = re.compile(r'(\${#include <(.*\.json)>})')

        if type(data) is dict:
            for key, value in data.iteritems():
                data[key] = self._sub_include(in_file, value, base_dir)
        elif type(data) is list or type(data) is type:
            for index, value in enumerate(data):
                data[index] = self._sub_include(in_file, value, base_dir)
        elif type(data) is str or type(data) is unicode:
            #print data, type(data)
            replaced = pattern.sub(lookup, data)
            if replaced is not None:
                return replaced
            else:
                return data

        return data


    def _get_json_data(self, json_in, parse_include=False,
                       base_dir=os.getcwd(),
                       os_env=False, env_opt={}):

        data = ""
        status = False

        self.logger.debug("Json input type %s value: %s", type(json_in), json_in if type(json_in) is str else "...")

        if type(json_in) == str or type(json_in) == unicode:
            if os.path.exists(os.path.abspath(json_in)):
                with open(json_in) as data_file:
                    self.logger.debug("Reading %s file content", json_in)
                    data = json.load(data_file)
                    status = True
            else:
                self.logger.error("File %s does not exist", json_in)
                return data, status

        elif type(json_in) == dict:
            data = json_in
            status = True
        else:
            self.logger.warn("Not supported type")
            return data, status

        def sub_include(in_file, data, base_dir):
            if not data:
                return data

            replaced = self._sub_include(in_file, data, base_dir)
            return data if replaced is None else replaced

        def sub_env(data, opt):
            if not opt or not data:
                return data
            replaced = self._sub_env(data, opt)

            return data if replaced is None else replaced

        if parse_include is True:
            self.logger.debug("Include sub is enabeld")
            data = sub_include(json_in, data, base_dir)

        if os_env is True:
            self.logger.debug("OS Env sub is enabeld")
            data = sub_env(data, os.environ)

        if env_opt:
            self.logger.debug("Optional Env sub is enabled")
            data = sub_env(data, env_opt)

        self.logger.debug("Returning satus %s", status)

        return data, status

    def __init__(self, schema, cfg, merge_list=[], extend_defaults=False,
                 parse_include=False, base_dir=os.getcwd(),
                 os_env=False, opt_env={}, logger=None):
        """
        Wrapper class for JSON parsing.

        :param schema: Schema file assosiated with JSON file. Should be a valid file name or Dict with schema contents.
        :param cfg: Config file in JSON format. Should be a valid file name or Dict with schema contents.
        :param merge_list: List of Dict's or JSON file names.
        :param extend_defaults: Set True if you want to merge defaults from schema file.
        :param os_env: Set True if you want to do Environment variable substitute.
        :param opt_env: Environment variable dict.

         After processing the input, json file will be flatten need by using "separator".
        """
        self.logger = logger or logging.getLogger(__name__)

        data, status = self._get_json_data(schema, parse_include, base_dir, os_env, opt_env)
        if status is False:
            self.logger.error("%s file not found\n" % schema)

        self.schema = data

        data, status = self._get_json_data(cfg, parse_include, base_dir, os_env, opt_env)
        if status is False:
            self.logger.error("%s file not found\n" % cfg)

        for entry in merge_list:
            mergedata, status = self._get_json_data(entry, parse_include, base_dir, os_env, opt_env)
            if status is False:
                self.logger.error("%s invalid merge files\n" % mergedata)

            result = merge(data, mergedata)

            data = result

        if extend_defaults is True:
            FillDefaultValidatingDraft4Validator = self._extend_with_default(Draft4Validator)
            FillDefaultValidatingDraft4Validator(self.schema).validate(data)
        else:
            validate(data, self.schema)


        self.data = data

    def get_cfg(self):

        return self.data


    def gen_final_config(self, outfile=None):
        str_ = json.dumps(self.data, indent=4, sort_keys=True, separators=(',', ': '), ensure_ascii=False)
        # Write JSON file
        if outfile is not None:
            with io.open(outfile, 'w+', encoding='utf8') as outfileobj:
                outfileobj.write(to_unicode(str_))

        return str_



if __name__ == '__main__':

    logger = logging.getLogger(__name__)
    logging.basicConfig(format='%(message)s')
    logger.setLevel(logging.DEBUG)

    obj = JSONParser(schema='../config-spec/device-schema.json', cfg='../config/drgn410c-device.json',
                     extend_defaults=True, base_dir='../config', parse_include=True, logger=logger)

    print json.dumps(obj.data, indent=4, sort_keys=True)