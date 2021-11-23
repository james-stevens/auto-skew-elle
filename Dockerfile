FROM alpine:3.13

RUN rmdir /tmp /run
RUN ln -s /dev/shm /tmp
RUN ln -s /dev/shm /ram
RUN ln -s /dev/shm /run

RUN apk update
RUN apk upgrade

RUN apk add python3 nginx
RUN apk add py3-flask py3-mysqlclient py3-gunicorn py3-yaml

RUN rmdir /var/lib/nginx/tmp /var/log/nginx
RUN ln -s /dev/shm /var/lib/nginx/tmp
RUN ln -s /dev/shm /var/log/nginx
RUN ln -s /dev/shm /run/nginx

RUN mkdir -p /etc/inittab.d /etc/start.d/

RUN mkdir /opt/pems
COPY certkey.pem /opt/pems

RUN rm -f /etc/inittab
RUN ln -s /ram/inittab /etc/inittab
RUN ln -s /ram/nginx_ssl.conf /etc/nginx/nginx_ssl.conf

RUN mkdir -p /opt/htdocs /usr/local/etc
COPY index.html /opt/htdocs

COPY pylogger *.py /usr/local/bin/
RUN python3 -m compileall /usr/local/bin/
COPY start start_wsgi start_nginx start_syslogd /usr/local/bin/

CMD [ "/usr/local/bin/start" ]
