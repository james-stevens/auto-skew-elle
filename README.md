# Auto-Skew-Elle
Auto-Skew-Elle (AutoSQL) is a no-code rest/api for any MySQL Database

# Purpose
This project reads a MySQL database schema and automatically provide a Rest/API to that database
without the need to actually write any code.


# Work-in-Progress

Currently this is still in development


# Running this API

You can run it in test mode by simply running `./auto_sql.py`. Running this way runs it in test mode in a single thread on `127.0.0.1:5000`

- request
- mysqlclient
- yaml
- flask

Your python installation will need a few modules which it will complain about, if you don't have!
I built it & run it on Alpine v3.13 and use the `apk py3-` modules than come with Alpine.

To run it in production, you really need to run it through something like `nginx` & `gunicorn`. This has all been set up for you
in the form of a container.

You can make the container by running the script `./dkmk` and run it with `./dkrun`.

In both cases it will read its connection to MySQL from the environment variables

- MYSQL_CONNECT
- MYSQL_DATABASE
- MYSQL_USERNAME
- MYSQL_PASSWORD

`MYSQL_CONNECT` can be a unix socket name, or IP Address & port, in the format `[address]:[port]`.

The `dkrun` script uses `--env-file /usr/local/etc/autosql.env`, so expects you you have these environment variables in a file at `/usr/local/etc/autosql.env`

The container will, by default start five threads, but if you want more (or less) you can specify a number in the
environment variable `AUTO_SQL_SESSIONS`

To check the API is working, simply ask for the ROOT page and you should get something like this

	MySql-Auto-Rest/API: <database>

e.g. (for test mode)

	curl http://127.0.0.1:5000/

where `<database>` is the name of the database you have asked it to connect to

The documentation for the API itself is sufficiently complex, I have put it in a separate MD file.
