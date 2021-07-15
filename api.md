# The API

NOTE: A trailing `/` is not supported, so don't use it, please.


## `/v1` - Checking it works

This will return a banner, plus the name of the database, for exmaple

	MySql-Auto-Rest/API: my_mysql_db


## /v1/meta/schema - Get a copy of the full database schema

This will include soem additional information that was provided in the YML file

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

`size` is present for most types, but not all. For exmaple, it is not present for type `datetime`.

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
