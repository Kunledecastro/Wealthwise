FROM postgres:16-alpine
COPY 01-roles.sh /docker-entrypoint-initdb.d/01-roles.sh
# Strip Windows line endings (Git on Windows may add them) so the script runs on any host.
RUN sed -i 's/\r$//' /docker-entrypoint-initdb.d/01-roles.sh \
 && chmod 0755 /docker-entrypoint-initdb.d/01-roles.sh
