const reference = document.getElementById("swagger-ui");

SwaggerUIBundle({
  url: reference.dataset.openapiUrl,
  domNode: reference,
  deepLinking: true,
  persistAuthorization: false,
  queryConfigEnabled: false,
  validatorUrl: null,
});
