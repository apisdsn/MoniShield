# Extra Caddy sites for the "https" profile (deploy/Caddyfile.letsencrypt imports *.caddy from here).
# Files here are not committed: they name your own domains. Example deploy/sites/blog.caddy:
#
#   blog.example.com {
#   	encode zstd gzip
#   	header Strict-Transport-Security "max-age=31536000; includeSubDomains"
#   	reverse_proxy blog-web:3000
#   }
