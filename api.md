# The API

NOTE: A trailing `/` is not supported, so don't use it, please.

When you submit a request, you can submit JSON to modify / control that request. The properties within the JSON you submit will be referred to as "modifiers".


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

When you query a table it can either return a list of objects or keyed set of objects, with a key of your choice.
If you want it to return a keyed set of objects, you need to specify what key you want using the `by` modifier (see below).

In each object, it will include the pseudo column `:rowid:` which is a positive integer and acts as a row counter. If you query the rows in batches
this will give you a row position that is consistant across the different batches.

Here's an example of some returned rows

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

In this exmaple, the table `tickers` has two real columns called `ticker` and `google`, and the request would have included the modified `"by": "ticker"`
to make the rows returned as a keyed set of objects keyed on the property `ticker`, instead of a list of objects.

The same rows, without the `by` modifier would look like this

    {
      "tickers": [
        {
          "ticker": "AAPL",
          "google": "AAPL:NASDAQ",
          ":rowid:": 1
        },
        {
          "ticker": "AMZN",
          "google": "AMZN:NASDAQ",
          ":rowid:": 2
        },
      ]
    }

When you make the request, you can post JSON to modify the query.

## The `where` Modifier

The `where` modifier is translated into a `where` clause in the `select` query. A `where` can have any of the following sub-properties
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

This translates into the SQL `where` clause of `where ticker = "AAPL"`. If the `=` property has multiple sub-properties, they would
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

In a comparison you can provide a list type, in which case a match again any item in the list will be a match, i.e. an `OR` match.
For the `=` comparison this is equivilent to the SQL `in (...)` operator, however, this list format can be used for all operator types.

    {
      "where" : {
        "=": {
          "ticker": ["AAPL","AMZN"]
        }
      }
    }

will translate to `where ticker in ("AAPL","AMZN")`. The SQl `in` operator is effectively an `OR`, so if the comparson you are doing is (say) `regexp`
and the value is a list, this will be split into separate comparsons that are `OR`ed with each other.

for exmaple

	{
      "where" : {
        "like": { "ticker": ["A%","B%"] },
        "=": { "value": 5 }
      }
    }

this will be translated into `where ((ticker like "A%") or (ticker like "B%")) and (value = 5)`

However, the `where` modifier can also be given a list of objects, if this is the case, each item in the list is `OR`ed. For exmaple

    {
      "where" : [
        { "=":  { "ticker": ["TSLA", "AAPL" ] } },
        { ">=": { "value": 5 } }
      ]
    }

will translate to `where (ticker in ("AAPL","TSLA")) or (value >= 5)`.


If a table has a column that links to another table (as specified in the YAML file), you can make comparisons with values in the row it links to by specifying 
`[remote-table].[remote-column-name]` instead of `[local-column-name]`.


So lets say the `ticker` table can join to the `prices` table (using a join specified in the YAML file), then we could have a a query like this

    {
      "where" : {
        ">=": {
          "prices.current_price": 100.00 
        }
      }
    }

This would produce the SQL `join prices using(column-from-yaml-file) where prices.current_price >= 100.00`


NOTE: `:rowid:` is a virtual column can not be used in a `where` clause, but can be controlled using the `limit` and `skip` modifiers.

If the `where` clause is a `string` type instead of a list or object type, then the contents will be given directly to SQL.



## The `by` Modifier

The `by` property lets you specify that you wish to receive the rows returned as a keyed set of objects instead of a list of objects.

If you wish to access the data by a keyed index, then this may be better. However, if you specifically want the sort order to be preserved
you should have the rows returned as a list.

The `by` property can be either a list type or a string type, where a string is a comma separated list of one or more column names to use.
Or the `by` value can be a single string which specifies the name of a unique index of that table to use as the key.
The pseudo type `:rowid:` can also be used.

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

And this is how the exact same query would get returned if no `by` modifier has been used.

    {
      "tickers": [
        {
          "ticker": "AAPL",
          "google": "AAPL:NASDAQ",
          ":rowid:": 1
        },
        {
          "ticker": "AMZN",
          "google": "AMZN:NASDAQ",
          ":rowid:": 2
        }
      ]
    }

If more than one column is specified, their values are concatinated with a pipe (`|`) separator.


## The `order` Modifier

The `order` property specifies a list of columns to sort by. This can either be a list type or a comma separated string.

Unless you are splitting up a long list of items, using `limit` & `skip`, using both the `by` and `order` modifiers
does not make sense as keyed objects do not retain a sort order.


## The `limit` and `skip` Modifiers

If you are retrieving a lot of rows, it can be useful to retrieve them in batches of (say) 100 rows at a time.

`limit` says how many rows to return in each batch and `skip` specifies how many rows you have already retrieved, so can skip over.

You can use `limit` without `skip`, but you can not use `skip` without `limit`.

To ensure you do not get duplicate rows, if you are using `limit` & `skip` to pull the data in as batches, you *must* also specifiy a sort `order`.

When using `limit` and `skip` to retrieve in batches, the `:rowid:` will tell you where the row belongs in the entire list, not just
its position in any one batch.

When using `limit` & `skip` also using `by` and `order` can still be useful.


## The `join` Property

The `join` relies on the YAML file to know which columns in which tables can join to other tables.

If a column can join to another table, you name the source column in the `join` clause and the row from the foreign table will
retrieved and the foreign object will be used as the property of that column, instead of the column's raw value.

Example, with no `join` -> `{"where":{"=":{"ticker":"AAPL"}}}`

    {
      "trades": [
        {
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
        {
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
      ]
    }

And now adding `"join":"ticker"` -> `{ "join":"ticker", "where":{"=":{"ticker":"AAPL"}}}`

    {
      "trades": [
        {
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
        {
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
      ]
    }

Now the `ticker` column has been replaced by the corresponding object from the `tickers` table. The pseudo column `:join:`,
in the atached object, tells you which column in the foreign table had been used to make the join.

NOTE: this now means to get the value of the `ticker`, you must be addresses it as `data.trades[i].ticker.ticker`, instead of just
`data.trades[i].ticker` had there been no join.


The pseudo column name `:all:` can be used in the `join` clause to mean do all joins that are possible.  i.e. `{ "join": ":all:" }`


In the JSON you send, if you set the boolean property `join-basic` to `true`, then the joined data will be attached as separate table objects and you will
have to match them up in your code. This can be useful where a lot of rows join to a few rows that contain a lot of data. For exmaple, if the currency joined
to a table containing the exchange rate, it might be better to have this included once for each currency, instead of including it in every record.

In this case the `tickers` table has only a small amount of data, so repeating the rows for `AAPL` each time does not represent a large
overhead, but if the rows in `tickers` had been much bigger, it might have.

So the same output would look like this with the addition of `"join-basic": true`

    {
      "trades": [
        {
          "trade_id": 15,
          "ticker": "AAPL",
          "when_dt": "2021-01-04 14:33:00",
          "quantity": 50,
          "currency": "USD",
          "price": 132.82382,
          "exchange_rate": 1.36258,
          "total_cost_gbp": 4931.66,
          "account_held": "HL Shares",
          "spot_value_id": 25417059,
          "eod_spot_value_id": 25014831,
          "eow_spot_value_id": 23864478,
          ":rowid:": 1
        },
        {
          "trade_id": 20,
          "ticker": "AAPL",
          "when_dt": "2020-12-21 17:22:00",
          "quantity": 52,
          "currency": "USD",
          "price": 125.46501,
          "exchange_rate": 1.33547,
          "total_cost_gbp": 4946.11,
          "account_held": "HL Shares",
          "spot_value_id": 25417064,
          "eod_spot_value_id": 25014836,
          "eow_spot_value_id": 23864483,
          ":rowid:": 2
        }
      ],
      "tickers.ticker": {
        "AAPL": {
          "ticker": "AAPL",
          "google": "AAPL:NASDAQ"
        }
      }
    }


You can see this has reduced the amount of data that the server needs to return although, in this exmaple, not by a lot.

NOTE: the joined data will always be retuned as keyed objects, keyed on the column that was used in the join.

If you have restricted the number of rows to be returned using `limit` then only the rows that match ones that are actually returned
will be added on, but `limit` & `skip` will not directly affect the joined data.

NOTE: to show the data is joined data, not original table data, the table object name is the column that was joined to.

You will need to either look at the schema for the `trades` table, or simply hard code the relationship in order to match up the rows with the join data.
The object name for the joined data will always be the same as the column it was joined on.


# `DELETE /v1/data/[table]` - Delete Rows

The `delete` method is for deleteing rows in the database and supports adding the modifiers `where` and `limit`, which both take the exact same syntax as the `GET`/`POST` above.

If you only want to delete a single rows, it is highly recommended that you include the modifier `"limit": 1`.


The `delete` method will not return any rows, but return the single property `affected_rows` which will be a positive integer that
tells you how many rows were deleted.


# `PUT /v1/data/[table]` - Insert Rows

The `put` method is for inserting rows in the database and only supports the `set` modifier. For a `put` the type of the `set` data can either be an object, of a list of objects.

In either case the objects will be a series of column names & values. In either case, the data is always inserted into the database as a single `insert`,
either using a single line `insert` or a multi-line `insert`

    {
      "set": {
        "account_held": "Mine-2",
        "from_trade_id": 555,
        "currency": "XYZ"
      }
    }

This will translate into a single line insert like this - `insert into table-name set account_held="Mine-2",from_trade_id=555,currency="XYZ"`

    {
      "set": [
        {
          "account_held": "Mine-2",
          "from_trade_id": 555,
        },
        {
          "account_held": "Mine-3",
          "currency": "BGP"
        }
      ]
    }

This second example will translate into a multiline `insert`, this means either all the rows will get inserted into the database, or none
or the rows will.

Where a column exists in on list object, but not in others, the database value `NULL` will be used in rows where it does not exist. So
this example will translate into `insert into table-name(account_held,from_trade_id,currency) values ("Mine-2",555,NULL),("Mine-3",NULL,"BGP")`

If `NULL` is not allowed in any of the missing columns, then the entire `insert` will fail & no rows will be added to the database.

`put` also only returns the `affected_rows` property.


# `PATCH /v1/data/[table]` - Update Rows

The `patch` method is used for updating existing rows in the database and supports the `where`, `set` and `limit` modifiers.

Unlike the `patch` method, for the `put` method the `set` modifier can only be an object type and not a list of objects.

The `where` & `limit` syntax is exactly the same as for the `get`/`post` methods. Again, as per the `delete` method, if you are trying to only
update one row, you should include the modifier `"limit": 1`.

`patch` also only returns the `affected_rows` property.
