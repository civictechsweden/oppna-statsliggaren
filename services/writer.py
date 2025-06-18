import csv
import json


class Writer(object):
    @staticmethod
    def write_json(dict: dict | list, filename: str):
        with open(filename, "w") as fp:
            json_string = json.dumps(dict, ensure_ascii=False, indent=4).encode("utf-8")
            fp.write(json_string.decode())

    @staticmethod
    def write_csv(dict: list, filename: str):
        if not len(dict):
            return

        keys = dict[0].keys()

        with open(filename, "w", newline="") as output_file:
            dict_writer = csv.DictWriter(output_file, keys)
            dict_writer.writeheader()
            dict_writer.writerows(dict)

    @staticmethod
    def write_text(text: str, filename: str):
        with open(filename, "w") as fp:
            fp.write(text)
