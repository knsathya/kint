import json
import os
import re
from jsonschema import validators, validate, Draft4Validator, RefResolver
from jsonmerge import merge
import logging
import io
import collections


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

        if isinstance(data, collections.Mapping):
            for key, value in data.iteritems():
                data[key] = self._sub_env(value, env_opt)
        elif isinstance(data, (list, tuple)):
            for index, value in enumerate(data):
                data[index] = self._sub_env(value, env_opt)
        elif isinstance(data, (str, unicode)):
            replaced = pattern.sub(lookup, data)
            if replaced is not None:
                return replaced
            else:
                return data

        return data

    def _sub_include(self, in_file, data, base_dir):

        if not data:
            return data

        def pattern_match(data):
            def lookup(match):
                if len(match.groups()) > 1:
                    new_inc_file = os.path.abspath(os.path.join(base_dir, match.group(2)))
                    if new_inc_file == os.path.abspath(in_file):
                        self.logger.warn("Warning: Circular dependency detected %s included in %s",
                                         new_inc_file, os.path.abspath(in_file))
                    else:
                        new_data, new_status = self._get_json_data(new_inc_file, True, base_dir, True)
                        if new_status is True:
                            if len(match.groups()) > 3:
                                keys = match.group(4).split('/')
                                tmp = None
                                for key in keys:
                                    if key:
                                        tmp = new_data[key]
                                return tmp
                            else:
                                return new_data
                        else:
                            self.logger.warn("Not found valid data in %s", new_inc_file)

                return match.group(1)

            pattern = r'(\$\(#include <(.*\.json)(#/(.*))?>\))'
            matchobj = re.search(pattern, data, 0)

            if matchobj:
                return lookup(matchobj)
            else:
                return data

        if isinstance(data, collections.Mapping):
            for key, value in data.iteritems():
                data[key] = self._sub_include(in_file, value, base_dir)
        elif isinstance(data, (list, tuple)):
            for index, value in enumerate(data):
                data[index] = self._sub_include(in_file, value, base_dir)
        elif isinstance(data, (str, unicode)):
            replaced = pattern_match(data)
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

        self.logger.debug("Returning status %s", status)

        return data, status

    def __init__(self, schema, cfg, merge_list=[],
                 extend_defaults=False,
                 ref_resolver=False, ref_dir=os.getcwd(),
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
        self.data = None
        self.schema = None

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
            if ref_resolver is True:
                resolver = RefResolver('file://' + os.path.abspath(ref_dir) + '/', self.schema)
                self.logger.info(resolver.base_uri)
                FillDefaultValidatingDraft4Validator(self.schema, resolver=resolver).validate(data)
            else:
                FillDefaultValidatingDraft4Validator(self.schema).validate(data)
        else:
            if ref_resolver is True:
                resolver = RefResolver('file://' + os.path.abspath(ref_dir) + '/', self.schema)
                Draft4Validator(schema, resolver=resolver).validate(data)
            else:
                validate(data, self.schema)


        self.data = data

    def get_cfg(self):
        return self.data

    def print_cfg(self):
        self.logger.info(json.dumps(self.data, indent=4, sort_keys=True, separators=(',', ': '), ensure_ascii=False))

    def print_schema(self):
        self.logger.info(json.dumps(self.schema, indent=4, sort_keys=True, separators=(',', ': '), ensure_ascii=False))

    def gen_final_config(self, outfile=None):
        str_ = json.dumps(self.data, indent=4, sort_keys=True, separators=(',', ': '), ensure_ascii=False)
        # Write JSON file
        if outfile is not None:
            with io.open(outfile, 'w+', encoding='utf8') as outfileobj:
                outfileobj.write(to_unicode(str_))

        return str_

    def dump_cfg(self, outfile):
        with open(outfile, 'w+') as fobj:
            json.dump(self.data, fobj, indent=4, sort_keys=True, separators=(',', ': '), ensure_ascii=False)

    def dump_schema(self, outfile):
        with open(outfile, 'w+') as fobj:
            json.dump(self.schema, fobj, indent=4, sort_keys=True, separators=(',', ': '), ensure_ascii=False)


if __name__ == '__main__':

    logger = logging.getLogger(__name__)
    logging.basicConfig(format='%(message)s')
    logger.setLevel(logging.DEBUG)

    obj = JSONParser(schema='../config/kint-schema.json', cfg='../config/dev-bkc-staging.json',
                     extend_defaults=True,
                     ref_resolver=True, ref_dir='../config',
                     base_dir='../config', parse_include=True,
                     os_env=True, opt_env={},
                     logger=logger)

    print json.dumps(obj.data, indent=4, sort_keys=True)