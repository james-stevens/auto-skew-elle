#! /usr/bin/python3
""" provide a rest/api to a MySQL Database using Flask """

import json
import os
from datetime import datetime
from MySQLdb import _mysql
from MySQLdb.constants import FIELD_TYPE
import MySQLdb.converters
import flask

import mysql_schema

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
    """ Convery MySQL string to JSON """
    if isinstance(data, bytes):
        return data.decode("utf8")
    return data


def mysql_connect():
    """ Connect to the database """
    for var in MYSQL_ENV:
        if var not in os.environ:
            return None

    my_conv = MySQLdb.converters.conversions.copy()
    my_conv[FIELD_TYPE.VARCHAR] = convert_string
    my_conv[FIELD_TYPE.CHAR] = convert_string
    my_conv[FIELD_TYPE.STRING] = convert_string
    my_conv[FIELD_TYPE.VAR_STRING] = convert_string

    return _mysql.connect(
        user=os.environ["MYSQL_USERNAME"],
        passwd=os.environ["MYSQL_PASSWORD"],
        unix_socket=os.environ["MYSQL_CONNECT"],
        db=os.environ["MYSQL_DATABASE"],
        conv=my_conv,
        charset='utf8mb4',
        init_command='SET NAMES UTF8',
    )


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


def add_data(data, this_col):
    """ convert {data} to SQL string """
    if this_col["is_plain_int"]:
        return str(int(data))
    if this_col["type"] == "boolean":
        return "1" if data else "0"
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


def prepare_row_data(rows, table):
    """ format {rows} from {table} for JSON output """
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
    """ JSON format {data} from {table}.{column} """
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


def find_join_column(src_table,dst_table):
    for col in schema[src_table]["columns"]:
        this_col = schema[src_table]["columns"][col]
        if "join" in this_col and this_col["join"]["table"] == dst_table:
            return col
    return None


def find_foreign_column(sql_joins, src_table, col):
    dst = col.split(".")

    if len(dst) != 2:
        flask.abort(400,{"error":"Invalid column name `{col}`".format(col=col)})

    if dst[0] in schema[src_table]["columns"] and "join" in schema[src_table]["columns"][dst[0]]:
        src_col = schema[src_table]["columns"][dst[0]]
        alias = "__zz__" + dst[0]
        col = alias + "." + dst[1]
        if alias in sql_joins:
            return col, src_col["join"]["table"]

        sql_joins[alias] = "join {dsttbl} {alias} on({srctbl}.{srccol}={alias}.{dstcol})".format(
            dsttbl = src_col["join"]["table"],
            dstcol = src_col["join"]["column"],
            alias=alias, srctbl = src_table, srccol = dst[0])
        return col, src_col["join"]["table"]

    col_name = find_join_column(src_table,dst[0])
    if col_name is None:
        flask.abort(400,{"error":"Could not find a join for `{col}` to `{tbl}`".format(col=col,tbl=src_table)})

    alias = "__zz__" + col_name
    col = alias + "." + dst[1]

    if alias in sql_joins:
        return col, dst[0]

    this_col = schema[src_table]["columns"][col_name]
    sql_joins[alias] = "join {dsttbl} {alias} on({srctbl}.{srccol}={alias}.{dstcol})".format(
        alias=alias,srctbl=src_table,srccol=col_name,dsttbl=dst[0],dstcol=this_col["join"]["column"])

    return col, dst[0]



def where_clause(table, where_data):
    """ convert the {where_data} JSON into SQL """
    if where_data is None:
        return ""

    this_cols = schema[table]["columns"]
    sql_joins = {}
    where = []
    for ask_item in ASKS:
        if ask_item not in where_data:
            continue

        for where_itm in where_data[ask_item]:
            alias = table
            tbl = table
            col = where_itm
            if where_itm.find(".") >= 0:
                col, tbl = find_foreign_column(sql_joins, table, col)
            elif col not in this_cols:
                flask.abort(
                    400, {
                        "error":
                        "Column `{col}` is not in table `{tbl}`".format(
                            col=col, tbl=table)
                    })

            clause = []
            for itm in clean_list_string(where_data[ask_item][where_itm]):
                clause.append(col + ASKS[ask_item] + add_data(itm, schema[tbl]["columns"][col.split(".")[1]]))

            where.append("(" + " or ".join(clause) + ")")

    return " ".join([ sql_joins[x] for x in sql_joins]) + (" where " + " and ".join(where)) if len(where) > 0 else ""


def plain_value(data):
    """ extract data item from {data} """
    if not isinstance(data, dict):
        return str(data)
    if ":value:" in data:
        return data[":value:"]
    if ":join:" in data:
        return data[data[":join:"].split(".")[1]]
    return str(data)


def include_for_join(data):
    """ shall we retrieve this foreign record """
    if data is None:
        return False
    if isinstance(data, str) and data == "":
        return False
    return True


def load_all_joins(need):
    """ Load all db data for joins {need}ed """
    join_data = {}
    for item in need:
        src = item.split(".")
        sql = "select * from " + src[0] + " where " + item + " in ("

        this_col = schema[src[0]]["columns"][src[1]]

        clauses = [add_data(d, this_col) for d in need[item]]

        if len(clauses) <= 0:
            continue

        sql = sql + ",".join(clauses) + ")"

        cnx.query(sql)
        res = cnx.store_result()
        ret = res.fetch_row(maxrows=0, how=1)
        prepare_row_data(ret, src[0])

        join_data[item] = {
            clean_col_data(cols[src[1]], src[0], src[1]): cols
            for cols in ret if src[1] in cols
        }

    return join_data


def join_this_column(table, col, which):
    """ do we want join data for this {table.col} """

    if which is None or len(which) == 0:
        return None

    this_col = schema[table]["columns"][col]
    if "join" not in this_col:
        return None

    if ":all:" in which or col in which:
        return this_col["join"]["table"] + "." + this_col["join"]["column"]

    return None


def handle_joins(data, which, basic_format):
    """ retrive foreign rows & merge into return {data} """
    if ":more:" not in schema or "joins" not in schema[":more:"]:
        return

    need = {}
    for table in data:
        for row in data[table]:
            for col in data[table][row]:
                if not include_for_join(data[table][row][col]):
                    continue
                target = join_this_column(table, col, which)
                if target is None:
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
    """ replace a columns data with retrived foreign record """
    for table in data:
        for row in [r for r in data[table]]:
            for col in [c for c in data[table][row]]:
                target = join_this_column(table, col, which)
                if target is not None and target in join_data:
                    if data[table][row][col] in join_data[target]:
                        data[table][row][col] = join_data[target][data[table]
                                                                  [row][col]]
                        data[table][row][col][":join:"] = target


def unique_id(best_idx, row):
    """ format the index item for {row} """
    return "|".join([plain_value(row[idx]) for idx in best_idx])


cnx = mysql_connect()
schema = mysql_schema.load_db_schema(cnx)
application = flask.Flask("MySQL-Rest/API")


@application.route("/")
def hello():
    """ respond with a `hello` to confirm working """
    return "MySql-Auto-Rest/API\n\n"


@application.route("/meta/v1/reload")
def reload_schema():
    """ reload the schema """
    global schema
    schema = mysql_schema.load_db_schema(cnx)
    return json.dumps(schema), 200


@application.route("/meta/v1/schema")
def give_schema():
    """ respond with full schema """
    return json.dumps(schema), 200


@application.route("/meta/v1/schema/<table_name>")
def give_table_schema(table_name):
    """ respond with schema for one <table> """
    if table_name not in schema:
        flask.abort(404, {"error": "Table not found"})
    return json.dumps(schema[table_name]), 200


@application.route("/data/v1/<table_name>", methods=['GET'])
def get_table_row(table_name):
    """ run select queries """
    if table_name not in schema:
        flask.abort(404, {"error": "Table not found"})

    sent = flask.request.json if flask.request.json is not None else {}
    sql = "select {tbl}.* from {tbl} ".format(tbl=table_name)
    sql = sql + where_clause(table_name, sent)
    print(">>>>",sql)

    cnx.query(sql)
    res = cnx.store_result()
    ret = res.fetch_row(maxrows=0, how=1)
    if len(ret) <= 0:
        flask.abort(404, {"error": "No Rows returned"})

    prepare_row_data(ret, table_name)

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
        join = sent["join"]
        if isinstance(join,bool):
            join = [":all:"] if join else None
        if join is not None:
            handle_joins(ret, clean_list_string(join),
                         ("join-basic" in sent and sent["join-basic"]))

    return json.dumps(ret), 200


if __name__ == "__main__":
    application.run()
    cnx.close()
