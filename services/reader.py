import csv
import json


def open_csv(filename: str) -> list:
    try:
        with open(filename, "r", newline="") as f:
            dict_reader = csv.DictReader(f)
            return list(dict_reader)
    except FileNotFoundError:
        return []


def open_json(filename: str) -> list | dict:
    try:
        file = open(filename)
    except FileNotFoundError:
        print("File not found")
        return []

    return json.load(file)
