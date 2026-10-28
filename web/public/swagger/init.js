// Swagger UI for /api/docs (MoniShield). A separate file because the CSP forbids inline scripts.
// Session = cookie from the same login page (sent automatically, same origin). Requests that change data need the
// X-Requested-With header (CSRF guard, TRD §8.2): added here so "Try it out" works.
window.addEventListener('DOMContentLoaded', () => {
  window.ui = window.SwaggerUIBundle({
    url: '/api/openapi.json',
    dom_id: '#swagger-ui',
    deepLinking: true,
    validatorUrl: null,          // do not contact validator.swagger.io
    tryItOutEnabled: false,
    persistAuthorization: false,
    displayRequestDuration: true,
    docExpansion: 'list',
    filter: true,
    requestInterceptor: (req) => { req.headers['X-Requested-With'] = 'monishield-docs'; req.credentials = 'same-origin'; return req; },
    responseInterceptor: (res) => { if (res.status === 401) window.location.replace('/?next=/api/docs'); return res; },
  });
});
