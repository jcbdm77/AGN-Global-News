FROM postgres:16-alpine
RUN apk add --no-cache gnupg
COPY backup.sh /backup.sh
ENTRYPOINT ["sh", "/backup.sh"]
