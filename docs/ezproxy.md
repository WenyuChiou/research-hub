# EZproxy PDF Access

EZproxy support is opt-in and only affects `paper attach-pdfs`.

1. Set your institution's URL template. It must contain `{encoded_url}`:

   ```bash
   research-hub config set ezproxy_url_template "https://login.example.edu/login?qurl={encoded_url}"
   ```

   If your library uses EZproxy, the template is usually visible after you
   click a publisher link from the library portal. Replace the target article
   URL with `{encoded_url}`.

2. Run the browser login once:

   ```bash
   research-hub ezproxy login
   ```

3. Verify state:

   ```bash
   research-hub ezproxy status
   ```

4. Re-run `paper attach-pdfs`. Paywalled publisher PDF URLs now try the proxy
   first and fall back to the direct URL on any proxy failure.

Cookies usually last 1-4 weeks before your institution requires re-login.
