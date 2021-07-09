#! /usr/bin/python3
""" provide a rest/api to a MySQL Database using Flask """

import json
import os
import yaml

INTS = ["tinyint", "int", "bigint"]


def load_more_schema(new_schema):
    """ load users file of additional schema information """
    new_schema[":more:"] = {}
    filename = "/usr/local/etc/" + os.environ["MYSQL_DATABASE"] + ".yml"
    if os.path.isfile(filename):
        with open(filename) as file:
            data = file.read()
            new_schema[":more:"] = yaml.load(data, Loader=yaml.FullLoader)
            return

    filename = os.environ["MYSQL_DATABASE"] + ".js"
    if os.path.isfile(filename):
        with open(filename) as file:
            data = file.read()
            new_schema[":more:"] = json.loads(data)


def add_join_items(new_schema):
    """ add `join` items to columns that join """
    jns = new_schema[":more:"]["joins"]
    for table in [t for t in new_schema]:
        if table[0] != ":":
            for col in [c for c in new_schema[table]["columns"]]:
                dst = find_join_dest(table, col, jns)
                if dst is not None:
                    tblcol = dst.split(".")
                    new_schema[table]["columns"][col]["join"] = {
                        "table": tblcol[0],
                        "column": tblcol[1]
                    }


def load_db_schema(cnx):
    """ Load/Reload database schema """
    new_schema = {}
    load_more_schema(new_schema)
    get_db_schema(cnx, new_schema)
    if ":more:" in new_schema and "joins" in new_schema[":more:"]:
        add_join_items(new_schema)
    return new_schema


def test_plain_int(this_type, this_places):
    """ return True if {this_type} with {this_places}
        # of decimal places is in INT """
    if this_type in INTS:
        return True
    if this_type == "decimal" and this_places == 0:
        return True
    return False


def find_join_dest(table, col, jns):
    """ does this {rable.col} have join dest in {jns} """
    long = table + "." + col
    if long in jns and jns[long] != long:
        return jns[long]
    if col in jns and jns[col] != long:
        return jns[col]
    return None


def sort_by_field(i):
    """ return 'Field' item for sorting """
    return i["Field"]


def schema_of_col(new_schema, col):
    """ convert MySQL column description into JSON schema """
    this_field = {}
    this_type = col["Type"].decode("utf8")
    this_places = 0
    if this_type.find(" unsigned") >= 0:
        this_type = this_type.split()[0]
        this_field["unsigned"] = True

    pos = this_type.find("(")
    if pos >= 0:
        this_size = this_type[pos + 1:-1]
        this_type = this_type[:pos]
        if this_size.find(",") >= 0:
            tmp = this_size.split(",")
            this_field["size"] = int(tmp[0])
            this_field["places"] = int(tmp[1])
            this_places = int(tmp[1])
        else:
            if ((int(this_size) == 1 and this_type == "tinyint") or
                (":more:" in new_schema
                 and "is_boolean" in new_schema[":more:"]
                 and col["Field"] in new_schema[":more:"]["is_boolean"])):
                this_type = "boolean"
                if "unsigned" in this_field:
                    del this_field["unsigned"]
            else:
                this_field["size"] = int(this_size)

    this_field["type"] = this_type
    if col["Extra"] == "auto_increment":
        this_field["serial"] = True

    this_field["null"] = (col["Null"] == "YES")
    plain_int = test_plain_int(this_type, this_places)
    this_field["is_plain_int"] = plain_int
    if col["Default"] is not None:
        defval = col["Default"]
        if plain_int:
            defval = int(defval)
        elif this_type == "boolean":
            defval = (int(defval) == 1)
        else:
            defval = defval.decode("utf8")
        this_field["default"] = defval

    return this_field


def get_db_schema(cnx, new_schema):
    """ Read schema from database """
    cnx.query("show tables")
    res = cnx.store_result()
    ret = res.fetch_row(maxrows=0, how=1)

    tbl_title = "Tables_in_" + os.environ["MYSQL_DATABASE"]
    for table in ret:
        new_schema[table[tbl_title]] = {}

    for table in new_schema:
        if table[0] == ":":
            continue

        cnx.query("describe " + table)
        res = cnx.store_result()
        ret = res.fetch_row(maxrows=0, how=1)
        new_schema[table]["columns"] = {}
        cols = [r for r in ret]
        cols.sort(key=sort_by_field)
        for col in cols:
            new_schema[table]["columns"][col["Field"]] = schema_of_col(
                new_schema, col)
        add_indexes_to_schema(cnx, new_schema, table)
    return new_schema


def add_indexes_to_schema(cnx, new_schema, table):
    """ Add index info for {table} to {new_schema} """
    cnx.query("show index from " + table)
    res = cnx.store_result()
    ret = res.fetch_row(maxrows=0, how=1)
    new_schema[table]["indexes"] = {}
    for col in ret:
        key = col["Key_name"] if col["Key_name"] != "PRIMARY" else ":primary:"
        if key not in new_schema[table]["indexes"]:
            new_schema[table]["indexes"][key] = {}
            new_schema[table]["indexes"][key]["columns"] = []
        new_schema[table]["indexes"][key]["columns"].append(col["Column_name"])
        new_schema[table]["indexes"][key]["unique"] = col["Non_unique"] == 0
