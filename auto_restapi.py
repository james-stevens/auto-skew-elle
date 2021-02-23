#! /usr/bin/python3

import yaml
import json
import os
from MySQLdb import _mysql
from MySQLdb.constants import FIELD_TYPE
import MySQLdb.converters
import flask

from apscheduler.schedulers.background import BackgroundScheduler
from pytz import utc

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


def convert_string(data):
    if isinstance(data, bytes):
        return data.decode("utf8")
    return data


my_conv = MySQLdb.converters.conversions.copy()
my_conv[FIELD_TYPE.VARCHAR] = convert_string
my_conv[FIELD_TYPE.CHAR] = convert_string
my_conv[FIELD_TYPE.STRING] = convert_string
my_conv[FIELD_TYPE.VAR_STRING] = convert_string

more_schema = {}
filename = os.environ["MYSQL_DATABASE"] + ".yml"
if os.path.isfile(filename):
    with open(filename) as fd:
        data = fd.read()
        more_schema = yaml.load(data, Loader=yaml.FullLoader)
else:
    filename = os.environ["MYSQL_DATABASE"] + ".js"
    if os.path.isfile(filename):
        with open(filename) as fd:
            data = fd.read()
            more_schema = json.loads(data)


def reload_db_schema():
    global schema
    schema = get_schema()


scheduler = BackgroundScheduler(timezone=utc)
job = scheduler.add_job(reload_db_schema,
                        'interval',
                        minutes=60,
                        id="ReloadSchema")
scheduler.start()


def mysql_connect():
    for m in MYSQL_ENV:
        if m not in os.environ:
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
    return i["Field"]


def get_schema():
    cnx.query("show tables")
    res = cnx.store_result()
    ret = res.fetch_row(maxrows=0, how=1)

    schema = {}

    n = "Tables_in_" + os.environ["MYSQL_DATABASE"]

    schema = {t[n]: {} for t in ret}

    for t in schema:
        cnx.query("describe " + t)
        res = cnx.store_result()
        ret = res.fetch_row(maxrows=0, how=1)
        schema[t]["columns"] = {}
        cols = [r for r in ret]
        cols.sort(key=sort_by_field)
        for r in cols:

            field = r["Field"]
            schema[t]["columns"][field] = {}
            tp = r["Type"].decode("utf8")
            if tp.find(" unsigned") >= 0:
                tp = tp.split()[0]
                schema[t]["columns"][field]["unsigned"] = True

            pos = tp.find("(")
            if pos >= 0:
                sz = tp[pos + 1:-1]
                tp = tp[:pos]
                if sz.find(",") >= 0:
                    x = sz.split(",")
                    schema[t]["columns"][field]["size"] = int(x[0])
                    schema[t]["columns"][field]["places"] = int(x[1])
                else:
                    if int(sz) == 1 and tp == "tinyint":
                        tp = "boolean"
                    else:
                        schema[t]["columns"][field]["size"] = int(sz)

            schema[t]["columns"][field]["type"] = tp
            if r["Extra"] == "auto_increment":
                schema[t]["columns"][field]["serial"] = True

            schema[t]["columns"][field]["null"] = (r["Null"] == "YES")
            if r["Default"] is not None:
                defval = r["Default"]
                if tp in INTS:
                    defval = int(defval)
                elif tp == "boolean":
                    defval = (int(defval) == 1)
                else:
                    defval = defval.decode("utf8")
                schema[t]["columns"][field]["default"] = defval

        cnx.query("show index from " + t)
        res = cnx.store_result()
        ret = res.fetch_row(maxrows=0, how=1)
        schema[t]["indexes"] = {}
        for r in ret:
            key = r["Key_name"] if r["Key_name"] != "PRIMARY" else ":primary:"
            if key not in schema[t]["indexes"]:
                schema[t]["indexes"][key] = {}
                schema[t]["indexes"][key]["columns"] = []
            schema[t]["indexes"][key]["columns"].append(r["Column_name"])
            schema[t]["indexes"][key]["unique"] = r["Non_unique"] == 0

    return schema


def find_best_index(idxes):
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


def add_data(data,is_int):
    if is_int:
        return str(int(data))
    else:
        if not isinstance(data, str):
            data = str(data)
        return ("unhex('" + "".join([hex(ord(a))[2:] for a in data]) + "')")


def clean_list_string(data):
    if isinstance(data,list):
        return data
    if isinstance(data,str) and data.find(","):
        return data.split(",")
    return [ data ]


def clean_row(rows,this_cols):
    for row in rows:
        for col in [r for r in row]:
            if row[col] is None:
                del row[col]
            else:
                row[col] = clean_col_data(row[col],this_cols[col]["type"])
                if "enums" in more_schema and col in more_schema["enums"] and row[col] in more_schema["enums"][col]:
                    row[col + ".text"] = more_schema["enums"][col][row[col]]


def clean_col_data(data,this_type):
    if data is None:
        return None

    if this_type == "boolean":
        return (int(data) != 0)

    if this_type in INTS:
        return int(data)

    if not isinstance(str, str):
        return str(data)

    return data


def where_clause(this_cols, js):
    if js is None:
        return ""

    where = []
    for a in ASKS:
        if a not in js:
            continue
        for col in this_cols:
            if col not in js[a]:
                continue

            is_int = (this_cols[col]["type"] in INTS)

            data = clean_list_string(js[a][col])
            clause = []
            for d in data:
                clause.append(col + ASKS[a] + add_data(d,is_int))

            where.append("(" + " or ".join(clause) + ")")

    if len(where) == 0:
        return ""

    return " where " + " and ".join(where)


def unique_id(table_name, best_idx, row):
    ret = []
    for idx in best_idx:
        tmp = row[idx]
        if not isinstance(tmp, str):
            tmp = str(tmp)
        ret.append(tmp)
    return "|".join(ret)


def include_for_join(data):
    if data is None:
        return False
    if isinstance(data,str) and data == "":
        return False
    return True


def load_all_joins(need):
    join_data = {}
    for item in need:
        src = item.split(".")
        sql = "select * from " + src[0] + " where " + item + " in ("

        is_int = (schema[src[0]]["columns"][src[1]]["type"] in INTS)
        clauses = [ add_data(d,is_int) for d in need[item] if include_for_join(d) ]
        if len(clauses) <= 0:
            continue

        sql = sql + ",".join(clauses) + ")"

        cnx.query(sql)
        res = cnx.store_result()
        ret = res.fetch_row(maxrows=0, how=1)
        clean_row(ret,schema[src[0]]["columns"])
        join_data[item] = ret

    return join_data


def find_join_dest(table,col,jns):
    long = table + "." + col
    if long in jns:
        return True, jns[long]
    if col in jns:
        return True, jns[col]
    return False, None


def join_this_column(table,col,jns,which):
    if which is None:
        return False, None

    want, target = find_join_dest(table,col,jns)
    if not want:
        return False, None

    if ":ALL:" in which or col in which:
        return want, target

    return False, None


def handle_joins(data,which):
    if "joins" not in more_schema:
        return

    need = {}
    for table in data:
        for row in data[table]:
            for col in data[table][row]:
                want, target = join_this_column(table,col,more_schema["joins"],which)
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

    for table in data:
        for row in [ r for r in data[table]]:
            for col in [ c for c in data[table][row]]:
                want, target = join_this_column(table,col,more_schema["joins"],which)
                if want and target is not None and target in join_data:
                    dst = target.split(".")
                    for join_row in join_data[target]:
                        if join_row[dst[1]] == data[table][row][col]:
                            data[table][row][col + "->" + target] = join_row





cnx = mysql_connect()
schema = get_schema()
application = flask.Flask("MySQL-Rest/API")


@application.route("/")
def hello():
    return "Hello World!\n\n"


@application.route("/sql/v1/schema")
def give_schema():
    return flask.jsonify(schema), 200


@application.route("/sql/v1/schema/<table_name>")
def give_table_schema(table_name):
    if table_name not in schema:
        flask.abort(404, {"error": "Table not found"})

    return flask.jsonify(schema[table_name]), 200


@application.route("/sql/v1/<table_name>", methods=['GET'])
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

    clean_row(ret,this_cols)

    this_idxs = schema[table_name]["indexes"]
    idx_cols = None
    if "by" in sent:
        snt_by = sent["by"]
        if isinstance(snt_by,str) and snt_by in this_idxs:
            if "unique" in this_idxs[snt_by] and this_idxs[snt_by]["unique"]:
                idx_cols = this_idxs[snt_by]["columns"]
        else:
            idx_cols = clean_list_string(snt_by)

    if idx_cols is None:
        idx_cols = this_idxs[find_best_index(this_idxs)]["columns"]

    ret = { table_name: { unique_id(table_name, idx_cols, tmp): tmp for tmp in ret} }

    if "join" in sent:
        handle_joins(ret,clean_list_string(sent["join"]))

    return flask.jsonify(ret), 200


if __name__ == "__main__":
    application.run()
    cnx.close()
