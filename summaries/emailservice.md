## Overview
The emailservice microservice is responsible for sending order confirmation emails to users. It receives order details and a user's email address, renders an HTML email based on a template, and (in a non-dummy implementation) would send this email. It plays a crucial role in providing post-purchase communication to customers.

## Language & framework
Python, utilizing the gRPC framework for inter-service communication and Jinja2 for email templating.

## APIs exposed
*   **gRPC**
    *   `EmailService.SendOrderConfirmation`: Sends an order confirmation email to a specified address with order details.
    *   `Health.Check`: Standard gRPC health check to determine if the service is operational.
    *   `Health.Watch`: Standard gRPC health check to watch service status changes (though the current implementation explicitly marks it as `UNIMPLEMENTED`).

## Services it depends on
*   **OpenTelemetry Collector** (gRPC): For exporting tracing data, if `ENABLE_TRACING` is set. The endpoint is configured via `COLLECTOR_SERVICE_ADDR`.

## Core functionalities
*   Receives requests to send order confirmation emails.
*   Generates dynamic HTML content for order confirmation emails using a Jinja2 template.
*   Logs the receipt of email sending requests (in dummy mode).
*   Responds to gRPC health check requests.
*   Provides structured JSON logging for its operations.
*   Supports distributed tracing via OpenTelemetry (when enabled).

## Notable dependencies
*   **grpcio**: The core library for gRPC communication.
*   **jinja2**: Used for rendering HTML email templates from data.
*   **python-json-logger**: Provides structured JSON logging capabilities.
*   **OpenTelemetry (opentelemetry-distro, opentelemetry-instrumentation-grpc, opentelemetry-exporter-otlp-proto-grpc)**: For distributed tracing and exporting spans to an OpenTelemetry collector.
*   **google-api-core**, **google-auth**: Base Google API client libraries, likely for integrating with Google Cloud services (e.g., mail, tracing, profiling).

## Anything unusual
The service runs in a "dummy mode" where the actual cloud mail client for sending emails is explicitly marked as "not implemented". Instead, it uses a `DummyEmailService` that only logs the intent to send an email, rather than performing the actual sending operation. Additionally, the `googlecloudprofiler` integration is commented out in the provided code.