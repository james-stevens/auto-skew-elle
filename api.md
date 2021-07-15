# The API

NOTE: A trailing `/` is not supported, so don't use it, please.


## `/v1` - Checking it works

This will return a banner, plus the name of the database, for exmaple

  MySql-Auto-Rest/API: my_mysql_db


## /v1/meta/schema - Get a copy of the full database schema

This not only gives you the schema that was read from MySQL, but will also include some additional information that was provided in the YAML file

The returned JSON contains one object for each table, within that object there is a `columns` and `indexes` property.

### Columm Properties

Within the table's `column` property there is one property for each column. These individual column properties
can have 

- `size` - Integer, Length as given by MySQL, applies to numbers & strings, etc
- `type` - Mandatory, String, MySQL given type
- `null` - Mandatory, Boolean, Does this column allow null value
- `is_plain_int` - Mandatory, Boolean, True if an integer type or decimal type with `0` places
- `places` - Integer, if `is_plain_int` is false, specifices the number of decimal places
- `unsigned` - Boolean, Is this number unsigned - only present for unsigned numbers.
- `join` - Object, Has the properties `table` and `column` and specified the column in another table this column can be joined to
- `serial` - Boolean, True if this field is of MySQL type `AUTO_INCREMENT`

`size` is present for most types, but not all. For example, it is not present for type `datetime`.

Here's an example

      "ticker": {
        "size": 20,
        "type": "char",
        "null": true,
        "is_plain_int": false,
        "join": {
          "table": "tickers",
          "column": "ticker"
        }
      },


### Indexes Properties

For each index on the table there will be a property of that name in the `indexes` property. The Primary index usually
doesn't have a name in MySQL, so it is given the pseudo index name `:primary:`.

Each index will have two sub-properties called `columns` which is a list of the columns used to make that index and the 
propertty `unique` which is boolean & is true if the index is a unique index.

If there are no indexes the `indexes` object will be present, but empty. This is common for `views`.

Here's an example

    "indexes": {
      ":primary:": {
        "columns": [
          "ticker",
          "batch"
        ],
        "unique": true
      },
      "spot_price_id": {
        "columns": [
          "spot_price_id"
        ],
        "unique": true
      }
    }


## The `:more:` Property

In addition to one property for each table, the is also a pseudo table called `:more:` which contains additional information
that came in the YAML file.

The `:more:` property contains the exact contents of the YAML file, but in JSON format.



# `/v1/meta/schema/[table]` - Get the schema for a single table

This returns the schema in exactly the same format as above, but for just the one table.


# `/v1/meta/reload` - Reload the schema

If you request this URL, the API will reload the schema from the database. If you are running in a production envirnment with multiple
threads, then this may not be particularly useful, as you need to run it in each thread, but there's no way to be sure you have done this.
Therefore it would probably be better to just restart the container.



# `GET/POST /v1/data/[table]` - Query the Table

When you query a table it will return an object which has a property by the name of the table you have queried. Within that
there will be one property for each row returned and within that will be an object which contained each row.

The API will automatically look at the unique index of the table to pick a name to act as the owner for each row, but you
can override this.

It will also include the pseudo column `:rowid:` which is a positive integer and acts as a row counter. If you query the rows in batches
this will give you a row position that is consistant across the different batches.

Here's an example

    {
      "tickers": {
        "AAPL": {
          "ticker": "AAPL",
          "google": "AAPL:NASDAQ",
          ":rowid:": 1
        },
        "AMZN": {
          "ticker": "AMZN",
          "google": "AMZN:NASDAQ",
          ":rowid:": 2
        },
      }
    }

In this exmaple, the table `tickers` has two real columns called `ticker` and `google`.

When you make the request, you can post semo JSON to modify the query.

## The `where` Property

The `where` clause is translated into a `where` clause in the `select` query. A `where` can have any of the following sub-properties
`=`, `!=`, `<>`, `<`, `>`, `>=`, `<=`, `like`, `regexp` which specify the comparison you want to do, then within each of those
properties you can have a column name as a property and a value to compare it with.

For exmaple

    {
      "where" : {
        "=": {
          "ticker":"AAPL"
        }
      }
    }

This translates into the SQL `where` clause of `where ticker = "AAPL"`. If the `=` property had multiple sub-properties, they would
be `AND`'ed together

    {
      "where" : {
        "=": {
          "ticker":"AAPL",
          "value":5
        }
      }
    }

So, this would translate to `where ticker = "AAPL" and value = 5`.

If you provide multiple compairsons in the same where object, they are also `AND`'ed together.

However, the where clause can be given a list of objects, if this is the last, each item in the list is `OR`ed. For exmaple

    {
      "where" : [
        { "=":  { "ticker": "AAPL" } },
        { ">=": { "value": 5 } }
      ]
    }

will translate to `where (ticker = "AAPL") or (value >= 5)`.

In a comparison you can provide a list type, in which case a match again any item in the list will be a match, i.e. an `OR` match.
For the `=` comparison this is equivilent to the SQL `in (...)` operator, however, this list format can be used for all operator types.

    {
      "where" : {
        "=": {
          "ticker": ["AAPL","AMZN"]
        }
      }
    }

will translate to `where ticker in ("AAPL","AMZN")`

If a table has a column that links to another table, you can make comparisons with values in the row it links to by specifying 
`[remote-table].[remote-column-name]` instead of `[local-column-name]`.

NOTE: `:rowid:` can not be used in a `where` clause.

If the `where` clause is a `string` type instead of a list or object type, then the contents will be given directly to SQL.



## The `by` Property

The `by` property allows you to overide the automatic selection of property to be used as the object identified for each row.
The default will be the simplest unique key, preferably the primary key. If there are no unique keys, it will fall back to 
using the `:rowid:`.

The `by` property can be either a list type or a string type, where a string is a comma separated list of column names to use.

The pseudo type `:rowid:` can be used

Here's two exmaples `{ "by": "ticker" }` & `{ "by": ":rowid:" }`


Here's an exmaple, where `{ "by": ":rowid:" }` was specified

    {
      "tickers": {
        "1": {
          "ticker": "AAPL",
          "google": "AAPL:NASDAQ",
          ":rowid:": 1
        },
        "2": {
          "ticker": "AMZN",
          "google": "AMZN:NASDAQ",
          ":rowid:": 2
        }
      }
    }

If more than one column is specified, their values are concatinated with a pipe (`|`) separator.

As each row is a property of the `by` name, the sort order of the rows is irrelevant unless you are using the `:rowid:` as
the identifier.


## The `order` Property

The `order` property specifies a list of columns to sort by. This can either be a list type or a comma separated string.
 Current only decending sorts are supported.


## The `limit` and `skip` Properties

If you are retrieving a lot of rows, it can be useful to retrieve them in batches of (say) 100 rows at a time.

`limit` says how many rows to return in each batch and `skip` specifies how many rows you have already retrieved, so can skip over.

You can use `limit` without `skip`, but you can not use `skip` without `limit`.

To ensure you do not get duplicate rows, you *must* also specifiy a sort `order`.

When using `limit` and `skip` to retrieve in batches, the `:rowid:` will tell you where the row belongs in the entire list, not just
its position in any one batch.


## The `join` Property

The `join` relies on the YAML file to know which columns in which tables can join to other tables.

If a column can join to another table, you name that column in the `join` clause and the row from the foreign table will
retrieved and the foreign object will be used as the value of that column, instead of the column's value.

Example, with no `join` -> `{"where":{"=":{"ticker":"AAPL"}}}`

    {
      "trades": {
        "15": {
          "trade_id": 15,
          "ticker": "AAPL",
          "when_dt": "2021-01-04 14:33:00",
          "quantity": 50.0,
          "currency": "USD",
          "price": 132.82382,
          "exchange_rate": 1.36258,
          "total_cost_gbp": 4931.66,
          "account_held": "HL Shares",
          "spot_value_id": 25416678,
          "eod_spot_value_id": 25014831,
          "eow_spot_value_id": 23864478,
          ":rowid:": 1
        },
        "20": {
          "trade_id": 20,
          "ticker": "AAPL",
          "when_dt": "2020-12-21 17:22:00",
          "quantity": 52.0,
          "currency": "USD",
          "price": 125.46501,
          "exchange_rate": 1.33547,
          "total_cost_gbp": 4946.11,
          "account_held": "HL Shares",
          "spot_value_id": 25416683,
          "eod_spot_value_id": 25014836,
          "eow_spot_value_id": 23864483,
          ":rowid:": 2
        }
      }
    }

And now adding `"join":"ticker"` -> `{ "join":"ticker", "where":{"=":{"ticker":"AAPL"}}}`

    {
      "trades": {
        "15": {
          "trade_id": 15,
          "ticker": {
          "ticker": "AAPL",
          "google": "AAPL:NASDAQ",
          ":join:": "tickers.ticker"
          },
          "when_dt": "2021-01-04 14:33:00",
          "quantity": 50.0,
          "currency": "USD",
          "price": 132.82382,
          "exchange_rate": 1.36258,
          "total_cost_gbp": 4931.66,
          "account_held": "HL Shares",
          "spot_value_id": 25416805,
          "eod_spot_value_id": 25014831,
          "eow_spot_value_id": 23864478,
          ":rowid:": 1
        },
        "20": {
          "trade_id": 20,
          "ticker": {
          "ticker": "AAPL",
          "google": "AAPL:NASDAQ",
          ":join:": "tickers.ticker"
          },
          "when_dt": "2020-12-21 17:22:00",
          "quantity": 52.0,
          "currency": "USD",
          "price": 125.46501,
          "exchange_rate": 1.33547,
          "total_cost_gbp": 4946.11,
          "account_held": "HL Shares",
          "spot_value_id": 25416810,
          "eod_spot_value_id": 25014836,
          "eow_spot_value_id": 23864483,
          ":rowid:": 2
        }
      }
    }

