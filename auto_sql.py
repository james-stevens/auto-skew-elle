#! /usr/bin/python3
""" provide a rest/api to a MySQL Database using Flask """

import json
import os
import sys
from datetime import datetime
from MySQLdb import _mysql
from MySQLdb.constants import FIELD_TYPE
import MySQLdb.converters
import flask

import mysql_schema

MYSQL_ENV = [
    "MYSQL_USERNAME", "MYSQL_PASSWORD", "MYSQL_CONNECT", "MYSQL_DATABASE"
]
ASKS = ["=", "!=", "<>", "<", ">", ">=", "<=", "like", "regexp"]

schema = {}

tried_reconnet = False


def convert_string(data):
    """ Convery MySQL string to JSON """
    if isinstance(data, bytes):
        return data.decode("utf8")
    return data


def connect_to_mysql():
    """ Connect to the database """
    for var in MYSQL_ENV:
        if var not in os.environ or os.environ[var] == "":
            print(f"ERROR: Environment variable '{var}' is missing")
            return None

    my_conv = MySQLdb.converters.conversions.copy()
    my_conv[FIELD_TYPE.VARCHAR] = convert_string
    my_conv[FIELD_TYPE.CHAR] = convert_string
    my_conv[FIELD_TYPE.STRING] = convert_string
    my_conv[FIELD_TYPE.VAR_STRING] = convert_string
    sock="/tmp/mysql.sock"
    host = None
    port = None
    if "MYSQL_CONNECT" in os.environ:
        conn = os.environ["MYSQL_CONNECT"]
        if conn[0] == "/":
            sock = conn
        else:
            host = conn
            port = 3306
            if conn.find(":") >= 0:
                svr = conn.split(":")
                host = svr[0]
                port = int(svr[1])


    return _mysql.connect(
        user=os.environ["MYSQL_USERNAME"],
        passwd=os.environ["MYSQL_PASSWORD"],
        unix_socket=sock,
        host = host, port = port,
        db=os.environ["MYSQL_DATABASE"],
        conv=my_conv,
        charset='utf8mb4', init_command='SET NAMES UTF8',
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
    if data is None or column[0] == ":":
        return data

    this_col = schema[table]["columns"][column]
    if this_col["type"] == "boolean":
        return int(data) != 0

    if this_col["type"] == "decimal":
        return float(data)

    if this_col["is_plain_int"]:
        return int(data)

    if isinstance(data, datetime):
        return data.strftime('%Y-%m-%d %H:%M:%S')

    if not isinstance(data, str):
        return str(data)

    return data


def find_join_column(src_table, dst_table):
    """ return column in {src_table} used to join to {dst_table} """
    for col in schema[src_table]["columns"]:
        this_col = schema[src_table]["columns"][col]
        if "join" in this_col and this_col["join"]["table"] == dst_table:
            return col
    return None


def find_foreign_column(sql_joins, src_table, dstcol):
    """ add the {sql_joins} needed to join to destination {dstcol} """
    dst = dstcol.split(".")
    fmt = "join {dsttbl} {alias} on({srctbl}.{srccol}={alias}.{dstcol})"

    if len(dst) != 2:
        flask.abort(
            400, {"error": f"Invalid column name `{dstcol}`"})

    if dst[0] in schema[src_table]["columns"] and "join" in schema[src_table][
            "columns"][dst[0]]:
        src_col = schema[src_table]["columns"][dst[0]]
        alias = "__zz__" + dst[0]
        dstcol = alias + "." + dst[1]
        if alias in sql_joins:
            return dstcol, src_col["join"]["table"]

        sql_joins[alias] = fmt.format(dsttbl=src_col["join"]["table"],
                                      dstcol=src_col["join"]["column"],
                                      alias=alias,
                                      srctbl=src_table,
                                      srccol=dst[0])
        return dstcol, src_col["join"]["table"]

    col_name = find_join_column(src_table, dst[0])
    if col_name is None:
        flask.abort(
            400, {
                "error":
                f"Could not find a join for `{dstcol}` to `{src_table}`"
            })

    alias = "__zz__" + col_name
    dstcol = alias + "." + dst[1]

    if alias in sql_joins:
        return dstcol, dst[0]

    this_col = schema[src_table]["columns"][col_name]
    sql_joins[alias] = fmt.format(alias=alias,
                                  srctbl=src_table,
                                  srccol=col_name,
                                  dsttbl=dst[0],
                                  dstcol=this_col["join"]["column"])

    return dstcol, dst[0]


def each_where_obj(sql_joins, table, ask_item, where_obj):
    """ return `where` clauses for {where_obj} & comparison {ask_item} """
    where = []
    for where_itm in where_obj:
        tbl = table
        col = where_itm
        if where_itm.find(".") >= 0:
            col, tbl = find_foreign_column(sql_joins, table, col)
        elif col not in schema[table]["columns"]:
            flask.abort(
                400, {
                    "error":
                    f"Column `{col}` is not in table `{table}`"
                })

        if ask_item == "=" and isinstance(where_obj[where_itm],list):
            if (tbl not in schema) or (col not in schema[tbl]["columns"]):
                flask.abort(
                    400, {
                        "error":
                        f"Column `{col}` is not in table `{table}`"
                    })
            this_col = schema[tbl]["columns"][col]
            where.append("(" + where_itm + " in (" + ",".join([add_data(d,this_col) for d in where_obj[where_itm]]) + ") )")
        else:
            clause = []
            for itm in clean_list_string(where_obj[where_itm]):
                c = col if col.find(".") < 0 else col.split(".")[1]
                clause.append(
                    col + ask_item +
                    add_data(itm, schema[tbl]["columns"][c]))

            where.append("(" + " or ".join(clause) + ")")

    return " and ".join(where) if len(where) > 0 else ""


def where_clause(table, sent):
    """ convert the {where_data} JSON into SQL """
    if "where" not in sent:
        return ""

    sql_joins = {}

    if isinstance(sent["where"], str):
        return sent["where"]

    if isinstance(sent["where"], object):
        for ask_item in sent["where"]:
            if ask_item not in ASKS:
                flask.abort(
                    400, {
                        "error":
                        f"Comparison `{ask_item}` not supported"
                    })
            where = each_where_obj(sql_joins, table, ask_item,
                                   sent["where"][ask_item])

    return " ".join([sql_joins[x]
                     for x in sql_joins]) + (" where " +
                                             where) if len(where) > 0 else ""


def plain_value(data):
    """ extract data item from {data} """
    if not isinstance(data, dict):
        return str(data)
    if ":value:" in data:
        return data[":value:"]
    if "join" in data:
        return data[data["join"].split(".")[1]]
    return str(data)


def include_for_join(data):
    """ shall we retrieve this foreign record """
    if data is None:
        return False
    if isinstance(data, str) and data == "":
        return False
    return True


def run_query(sql):
    try:
        cnx.query(sql)

    except MySQLdb.ProgrammingError as e:
        flask.abort( 400, { "error": str(e) })

    except Exception as e:
        cnx.close()
        make_connection()
        try:
            cnx.query(sql)
        except Exception as e:
            sys.exit(1)


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
        run_query(sql)

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

    if which is None or len(which) == 0 or col[0] == ":":
        return None

    this_col = schema[table]["columns"][col]
    if "join" not in this_col:
        return None

    if ":all:" in which or col in which:
        return this_col["join"]["table"] + "." + this_col["join"]["column"]

    return None


def handle_joins(rows, which, basic_format):
    """ retrive foreign rows & merge into return {rows} """
    if ":more:" not in schema or "joins" not in schema[":more:"]:
        return

    need = {}
    for table in rows:
        for row in rows[table]:
            if isinstance(rows[table],list):
                cols = row
            else:
                cols = rows[table][row]

            for col in cols:
                if not include_for_join(cols[col]):
                    continue
                target = join_this_column(table, col, which)
                if target is None:
                    continue

                if target not in need:
                    need[target] = []

                if cols[col] not in need[target]:
                    need[target].append(cols[col])

    if len(need) <= 0:
        return

    join_data = load_all_joins(need)
    if basic_format:
        rows.update(join_data)
    else:
        add_join_data(rows, join_data, which)


def add_join_data(rows, join_data, which):
    """ replace a columns data with retrived foreign record """
    for table in rows:
        for row in [r for r in rows[table]]:
            if isinstance(rows[table],list):
                cols = row
            else:
                cols = rows[table][row]

            for col in [c for c in cols]:
                target = join_this_column(table, col, which)
                if target is not None and target in join_data:
                    if cols[col] in join_data[target]:
                        cols[col] = join_data[target][cols[col]]
                        cols[col][":join:"] = target

def unique_id(best_idx, row):
    """ format the index item for {row} """
    return "|".join([plain_value(row[idx]) for idx in best_idx])


def make_connection():
    global schema
    global cnx
    cnx = connect_to_mysql()
    if cnx is None:
        print("ERROR: Failed to connect to MySQL")
        sys.exit(1)

    schema = mysql_schema.load_db_schema(cnx)


def check_supplied_modifiers(sent,allowed):
    for s in sent:
        if s not in allowed:
            flask.abort(406, {"error": f"The modifier '${s}' is not supported in this request"})


application = flask.Flask("MySQL-Rest/API")
make_connection()


@application.route("/v1",methods=['GET'])
def hello():
    """ respond with a `hello` to confirm working """
    db = os.environ["MYSQL_DATABASE"]
    return f"MySql-Auto-Rest/API: {db}\n\n"


@application.route("/v1/meta/reload",methods=['GET'])
def reload_schema():
    """ reload the schema """
    global schema
    schema = mysql_schema.load_db_schema(cnx)
    return json.dumps(schema), 200


@application.route("/v1/meta/schema",methods=['GET'])
def give_schema():
    """ respond with full schema """
    return json.dumps(schema), 200


@application.route("/v1/meta/schema/<table>",methods=['GET'])
def give_table_schema(table):
    """ respond with schema for one <table> """
    if table not in schema:
        flask.abort(404, {"error": f"Table '${table}' does not exist"})
    return json.dumps(schema[table]), 200


def build_sql(table, sent, start_sql):
    """ build the SQL needed to run the users query on {table} """
    sql = start_sql + where_clause(table, sent)
    if "order" in sent:
        sql = sql + " order by " + ",".join(clean_list_string(sent["order"]))

    start = 0
    if "limit" in sent:
        sql = sql + " limit " + str(int(sent["limit"]))
        if "skip" in sent:
            start = int(sent["skip"])
            sql = sql + " offset " + str(start)
    else:
        if "skip" in sent:
            flask.abort(406,
                        {"error": "`skip` without `limit` is not allowed"})

    print(">>>>", sql)
    return start, sql


def get_sql_rows(sql, start):
    """ run the {sql} and return the rows """
    run_query(sql)
    res = cnx.store_result()
    rows = [r for r in res.fetch_row(maxrows=0, how=1)]
    if len(rows) <= 0:
        return {}, 200

    rowid = start + 1
    for row in rows:
        row[":rowid:"] = rowid
        rowid = rowid + 1

    return rows


def process_one_set(set_clasue,table):
    ret = []
    this_tbl = schema[table]
    cols = this_tbl["columns"]
    for s in set_clasue:
        if s not in cols:
            flask.abort(404,{"error":"Column ${s} not in table ${table}"})

        ret.append(s + "=" + add_data(set_clasue[s],cols[s]))
    return ret


def get_idx_cols(table, sent):
    """ get suitable list of index columns for {table} """
    idx_cols = None
    this_idxs = schema[table]["indexes"]
    if "by" in sent:
        snt_by = sent["by"]
        if isinstance(snt_by, str) and snt_by in this_idxs:
            if "unique" in this_idxs[snt_by] and this_idxs[snt_by]["unique"]:
                idx_cols = this_idxs[snt_by]["columns"]
        else:
            idx_cols = clean_list_string(snt_by)
            for idx in idx_cols:
                if not (idx == ":rowid:" or idx in schema[table]["columns"]):
                    flask.abort(400,
                                {"error": "Bad column name in `by` clause"})
    if idx_cols is None and len(this_idxs) > 0:
        idx_cols = this_idxs[find_best_index(this_idxs)]["columns"]

    if idx_cols is None:
        idx_cols = [":rowid:"]

    return idx_cols


@application.route("/v1/data/<table>", methods=['PATCH'])
def update_table_row(table):
    if table not in schema:
        flask.abort(404, {"error": f"Table '${table}' does not exist"})

    if (flask.request.json is None) or ("set" not in flask.request.json):
        flask.abort(400, {"error": "A `set` clause is mandatory for an UPDATE"})

    sent = flask.request.json
    check_supplied_modifiers(sent,["where","limit","set"])

    if not isinstance(sent["set"],dict):
        flask.abort(400, {"error": "In an UPDATE, the `set` clause must be an object type"})

    set_list = process_one_set(sent["set"],table)
    sql = f"update {table} set " + ",".join(set_list)
    start, sql = build_sql(table, sent, sql)

    cnx.query(sql)
    cnx.store_result()
    ret = cnx.affected_rows()
    return json.dumps({"affected_rows":ret}),200


@application.route("/v1/data/<table>", methods=['DELETE'])
def delete_table_row(table):
    if table not in schema:
        flask.abort(404, {"error": f"Table '${table}' does not exist"})

    if (flask.request.json is None) or ("where" not in flask.request.json):
        flask.abort(400, {"error": "A `where` clause is mandatory for a DELETE"})

    check_supplied_modifiers(flask.request.json,["where","limit"])

    start, sql = build_sql(table, flask.request.json, f"delete from {table} ")

    cnx.query(sql)
    cnx.store_result()
    ret = cnx.affected_rows()
    return json.dumps({"affected_rows":ret}),200


@application.route("/v1/data/<table>", methods=['GET','POST'])
def get_table_row(table):
    """ run select queries """
    if table not in schema:
        flask.abort(404, {"error": f"Table '${table}' does not exist"})

    sent = flask.request.json if flask.request.json is not None else {}
    check_supplied_modifiers(sent,["where","limit","skip","by","order","join","join-basic"])

    start, sql = build_sql(table, sent, f"select {table}.* from {table} ")
    sql_rows = get_sql_rows(sql, start)

    if not isinstance(sql_rows,list):
        return sql_rows

    prepare_row_data(sql_rows, table)

    if "by" in sent:
        ret_rows = {
            table:
            {unique_id(get_idx_cols(table, sent), tmp): tmp
             for tmp in sql_rows}
        }
    else:
        ret_rows = { table: sql_rows }

    if "join" in sent:
        join = sent["join"]
        if isinstance(join, bool):
            join = [":all:"] if join else None
        if join is not None:
            handle_joins(ret_rows, clean_list_string(join),
                         ("join-basic" in sent and sent["join-basic"]))

    return json.dumps(ret_rows), 200


if __name__ == "__main__":
    application.run()
    cnx.close()
