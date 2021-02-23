#! /usr/bin/python3

import json
import os
from datetime import datetime
import yaml
from MySQLdb import _mysql
from MySQLdb.constants import FIELD_TYPE
import MySQLdb.converters
import flask

INTS = ["tinyint", "int", "bigint"]
NUMBERS = INTS + ["decimal"]
MYSQL_ENV = [
    "MYSQL_USERNAME", "MYSQL_PASSWORD", "MYSQL_CONNECT", "MYSQL_DATABASE"
]
ASKS = {
    "equal": "=",
    "greater": ">",
    "less": "<",
    "greq": ">=",
    "lseq": "<=",
    "like": "like"
}

schema = {}


def convert_string(data):
    if isinstance(data, bytes):
        return data.decode("utf8")
    return data


my_conv = MySQLdb.converters.conversions.copy()
my_conv[FIELD_TYPE.VARCHAR] = convert_string
my_conv[FIELD_TYPE.CHAR] = convert_string
my_conv[FIELD_TYPE.STRING] = convert_string
my_conv[FIELD_TYPE.VAR_STRING] = convert_string


def load_more_schema(new_schema):
    """ load additional schema information """
    new_schema[":more:"] = {}
    filename = os.environ["MYSQL_DATABASE"] + ".yml"
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


def reload_db_schema():
    """ REload database schema """
    new_schema = get_schema()
    load_more_schema(new_schema)
    return new_schema


def test_plain_int(this_type, this_places):
    """ return True if {this_type} with {this_places} # of decimal places is in INT"""
    if this_type in INTS:
        return True
    if this_type == "decimal" and this_places == 0:
        return True
    return False


def mysql_connect():
    """ Connect to the database """
    for var in MYSQL_ENV:
        if var not in os.environ:
            return None

    return _mysql.connect(
        user=os.environ["MYSQL_USERNAME"],
        passwd=os.environ["MYSQL_PASSWORD"],
        unix_socket=os.environ["MYSQL_CONNECT"],
        db=os.environ["MYSQL_DATABASE"],
        conv=my_conv,
        charset='utf8mb4',
        init_command='SET NAMES UTF8',
    )


def sort_by_field(i):
    """ return 'Field' item for sorting """
    return i["Field"]


def get_schema():
    """ Read schema from database """
    cnx.query("show tables")
    res = cnx.store_result()
    ret = res.fetch_row(maxrows=0, how=1)

    new_schema = {}

    tbl_title = "Tables_in_" + os.environ["MYSQL_DATABASE"]

    new_schema = {table[tbl_title]: {} for table in ret}

    for table in new_schema:
        cnx.query("describe " + table)
        res = cnx.store_result()
        ret = res.fetch_row(maxrows=0, how=1)
        new_schema[table]["columns"] = {}
        cols = [r for r in ret]
        cols.sort(key=sort_by_field)
        for col in cols:

            field = col["Field"]
            new_schema[table]["columns"][field] = {}
            this_type = col["Type"].decode("utf8")
            this_places = 0
            if this_type.find(" unsigned") >= 0:
                this_type = this_type.split()[0]
                new_schema[table]["columns"][field]["unsigned"] = True

            pos = this_type.find("(")
            if pos >= 0:
                this_size = this_type[pos + 1:-1]
                this_type = this_type[:pos]
                if this_size.find(",") >= 0:
                    tmp = this_size.split(",")
                    new_schema[table]["columns"][field]["size"] = int(tmp[0])
                    new_schema[table]["columns"][field]["places"] = int(tmp[1])
                    this_places = int(tmp[1])
                else:
                    if int(this_size) == 1 and this_type == "tinyint":
                        this_type = "boolean"
                    else:
                        new_schema[table]["columns"][field]["size"] = int(
                            this_size)

            new_schema[table]["columns"][field]["type"] = this_type
            if col["Extra"] == "auto_increment":
                new_schema[table]["columns"][field]["serial"] = True

            new_schema[table]["columns"][field]["null"] = (
                col["Null"] == "YES")
            plain_int = test_plain_int(this_type, this_places)
            new_schema[table]["columns"][field]["is_plain_int"] = plain_int
            if col["Default"] is not None:
                defval = col["Default"]
                if plain_int:
                    defval = int(defval)
                elif this_type == "boolean":
                    defval = (int(defval) == 1)
                else:
                    defval = defval.decode("utf8")
                new_schema[table]["columns"][field]["default"] = defval
        add_schema_indexes(new_schema, table)
    return new_schema


def add_schema_indexes(new_schema, table):
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


def find_best_index(idxes):
    """ Find shortest / best index from list of {idxes} """
    if ":primary:" in idxes:
        return ":primary:"
    most_col = 100
    idx = None
    for i in idxes:
        ncols = len(idxes[i]["columns"])
        if "unique" in idxes[i] and idxes[i]["unique"] and ncols < most_col:
            most_col = ncols
            idx = i
    return idx


def add_data(data, is_int):
    """ convert {data} to SQL string """
    if is_int:
        return str(int(data))
    if not isinstance(data, str):
        data = str(data)
    return "unhex('" + "".join([hex(ord(a))[2:] for a in data]) + "')"


def clean_list_string(data):
    """ convert string or comma separated list to list """
    if isinstance(data, list):
        return data
    if isinstance(data, str) and data.find(","):
        return data.split(",")
    return [data]


def clean_row(rows, table):
    for row in rows:
        for col in [r for r in row]:
            if row[col] is None:
                del row[col]
            else:
                row[col] = clean_col_data(row[col], table, col)
                if ("enums" in schema[":more:"]
                        and col in schema[":more:"]["enums"]
                        and row[col] in schema[":more:"]["enums"][col]):
                    row[col] = {
                        ":value:": row[col],
                        ":text:": schema[":more:"]["enums"][col][row[col]]
                    }


def clean_col_data(data, table, column):
    if data is None:
        return None

    this_col = schema[table]["columns"][column]
    if this_col["type"] == "boolean":
        return int(data) != 0

    if this_col["is_plain_int"]:
        return int(data)

    if isinstance(data, datetime):
        return data.strftime('%Y-%m-%d %H:%M:%S')

    if not isinstance(data, str):
        return str(data)

    return data


def where_clause(this_cols, where_data):
    if where_data is None:
        return ""

    where = []
    for ask_item in ASKS:
        if ask_item not in where_data:
            continue
        for col in this_cols:
            if col not in where_data[ask_item]:
                continue

            data = clean_list_string(where_data[ask_item][col])
            clause = []
            for itm in data:
                clause.append(col + ASKS[ask_item] +
                              add_data(itm, this_cols[col]["is_plain_int"]))

            where.append("(" + " or ".join(clause) + ")")

    if len(where) == 0:
        return ""

    return " where " + " and ".join(where)


def plain_value(data):
    if not isinstance(data, dict):
        return str(data)
    if ":value:" in data:
        return data[":value:"]
    if ":join:" in data:
        tmp = data[":join:"].split(".")
        return data[tmp[1]]
    return str(data)


def unique_id(best_idx, row):
    ret = []
    for idx in best_idx:
        ret.append(plain_value(row[idx]))
    return "|".join(ret)


def include_for_join(data):
    if data is None:
        return False
    if isinstance(data, str) and data == "":
        return False
    return True


def load_all_joins(need):
    join_data = {}
    for item in need:
        src = item.split(".")
        sql = "select * from " + src[0] + " where " + item + " in ("

        is_int = schema[src[0]]["columns"][src[1]]["is_plain_int"]

        clauses = [
            add_data(d, is_int) for d in need[item] if include_for_join(d)
        ]

        if len(clauses) <= 0:
            continue

        sql = sql + ",".join(clauses) + ")"

        cnx.query(sql)
        res = cnx.store_result()
        ret = res.fetch_row(maxrows=0, how=1)
        clean_row(ret, src[0])

        join_data[item] = {
            clean_col_data(cols[src[1]], src[0], src[1]): cols
            for cols in ret if src[1] in cols
        }

    return join_data


def find_join_dest(table, col, jns):
    long = table + "." + col
    if long in jns and jns[long] != long:
        return True, jns[long]
    if col in jns and jns[col] != long:
        return True, jns[col]
    return False, None


def join_this_column(table, col, jns, which):
    if which is None or len(which) == 0:
        return False, None

    want, target = find_join_dest(table, col, jns)
    if not want:
        return False, None

    if ":all:" in which or col in which:
        return want, target

    return False, None


def handle_joins(data, which, basic_format):
    if "joins" not in schema[":more:"]:
        return

    need = {}
    for table in data:
        for row in data[table]:
            for col in data[table][row]:
                want, target = join_this_column(table, col,
                                                schema[":more:"]["joins"],
                                                which)
                if not want or target is None:
                    continue

                dst = target.split(".")
                if dst[0] == table and dst[1] == col:
                    continue
                if target not in need:
                    need[target] = []
                if data[table][row][col] not in need[target]:
                    need[target].append(data[table][row][col])

    if len(need) <= 0:
        return

    join_data = load_all_joins(need)
    if basic_format:
        data.update(join_data)
    else:
        add_join_data(data, join_data, which)


def add_join_data(data, join_data, which):
    for table in data:
        for row in [r for r in data[table]]:
            for col in [c for c in data[table][row]]:
                want, target = join_this_column(table, col,
                                                schema[":more:"]["joins"],
                                                which)
                if want and target is not None and target in join_data:
                    if data[table][row][col] in join_data[target]:
                        data[table][row][col] = join_data[target][data[table]
                                                                  [row][col]]
                        data[table][row][col][":join:"] = target


cnx = mysql_connect()
schema = reload_db_schema()
application = flask.Flask("MySQL-Rest/API")


@application.route("/")
def hello():
    return "MySql-Auto-Rest/API\n\n"


@application.route("/meta/v1/reload")
def reload_schema():
    global schema
    schema = reload_db_schema()
    return flask.jsonify(schema), 200


@application.route("/meta/v1/schema")
def give_schema():
    return flask.jsonify(schema), 200


@application.route("/meta/v1/schema/<table_name>")
def give_table_schema(table_name):
    if table_name not in schema:
        flask.abort(404, {"error": "Table not found"})

    return flask.jsonify(schema[table_name]), 200


@application.route("/data/v1/<table_name>", methods=['GET'])
def get_table_row(table_name):
    if table_name not in schema:
        flask.abort(404, {"error": "Table not found"})

    this_cols = schema[table_name]["columns"]

    sent = flask.request.json if flask.request.json is not None else {}
    sql = "select * from " + table_name
    sql = sql + where_clause(this_cols, sent)

    cnx.query(sql)
    res = cnx.store_result()
    ret = res.fetch_row(maxrows=0, how=1)
    if len(ret) <= 0:
        flask.abort(404, {"error": "No Rows returned"})

    clean_row(ret, table_name)

    this_idxs = schema[table_name]["indexes"]
    idx_cols = None
    if "by" in sent:
        snt_by = sent["by"]
        if isinstance(snt_by, str) and snt_by in this_idxs:
            if "unique" in this_idxs[snt_by] and this_idxs[snt_by]["unique"]:
                idx_cols = this_idxs[snt_by]["columns"]
        else:
            idx_cols = clean_list_string(snt_by)
            for idx in idx_cols:
                if idx not in schema[table_name]["columns"]:
                    flask.abort(400,
                                {"error": "Bad column name in `by` clause"})

    if idx_cols is None:
        idx_cols = this_idxs[find_best_index(this_idxs)]["columns"]

    ret = {table_name: {unique_id(idx_cols, tmp): tmp for tmp in ret}}

    if "join" in sent:
        handle_joins(ret, clean_list_string(sent["join"]),
                     ("join-basic" in sent and sent["join-basic"]))

    return flask.jsonify(ret), 200


if __name__ == "__main__":
    application.run()
    cnx.close()
