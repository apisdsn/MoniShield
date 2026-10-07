// Swagger UI untuk /api/docs (MoniShield). Berkas terpisah karena CSP melarang skrip sebaris.
// Sesi = cookie dari halaman login yang sama (dikirim otomatis, satu asal). Permintaan yang mengubah data butuh header
// X-Requested-With (penahan CSRF, TRD §8.2): ditambahkan di sini agar "Try it out" bekerja.
window.addEventListener('DOMContentLoaded', () => {
  window.ui = window.SwaggerUIBundle({
    url: '/api/openapi.json',
    dom_id: '#swagger-ui',
    deepLinking: true,
    validatorUrl: null,          // jangan menghubungi validator.swagger.io
    tryItOutEnabled: false,
    persistAuthorization: false,
    displayRequestDuration: true,
    docExpansion: 'list',
    filter: true,
    requestInterceptor: (req) => { req.headers['X-Requested-With'] = 'monishield-docs'; req.credentials = 'same-origin'; return req; },
    responseInterceptor: (res) => { if (res.status === 401) window.location.replace('/?next=/api/docs'); return res; },
  });
});
