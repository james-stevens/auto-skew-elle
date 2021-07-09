FROM alpine:3.13

RUN rmdir /tmp
RUN ln -s /dev/shm /tmp
RUN ln -s /dev/shm /ram

RUN apk update
RUN apk upgrade

RUN apk add python3 nginx
RUN apk add py3-flask py3-mysqlclient py3-gunicorn py3-yaml

RUN rmdir /var/lib/nginx/tmp /var/log/nginx
RUN ln -s /dev/shm /var/lib/nginx/tmp
RUN ln -s /dev/shm /var/log/nginx
RUN ln -s /dev/shm /run/nginx

COPY certkey.pem /etc/nginx/
RUN rm -f /etc/inittab
RUN ln -s /ram/inittab /etc/inittab
RUN ln -s /ram/nginx_ssl.conf /etc/nginx/nginx_ssl.conf

COPY *.py /usr/local/bin/
RUN python3 -m compileall /usr/local/bin/
COPY start start_wsgi start_nginx /usr/local/bin/

CMD [ "/usr/local/bin/start" ]
