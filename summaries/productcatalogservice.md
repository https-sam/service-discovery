## Overview
The `productcatalogservice` is responsible for managing and providing access to the product catalog. It allows other services to retrieve product listings, get details for individual products, and search for products based on keywords. The service acts as a central source for product information within the wider system.

## Language & framework
The primary language for this service is **Go** (Go 1.25.0, with toolchain Go 1.26.1). It utilizes the **gRPC** framework for inter-service communication.

## APIs exposed
The service exposes the following gRPC APIs:

*   **ProductCatalogService**:
    *   `ListProducts(Empty) returns (ListProductsResponse)`: Retrieves a list of all products in the catalog.
    *   `GetProduct(GetProductRequest) returns (Product)`: Fetches details for a specific product by its ID.
    *   `SearchProducts(SearchProductsRequest) returns (SearchProductsResponse)`: Searches for products based on a query string in their name or description.
*   **Health (grpc.health.v1)**:
    *   `Check(HealthCheckRequest) returns (HealthCheckResponse)`: Provides a health status check, returning `SERVING` if healthy.
    *   `Watch(HealthCheckRequest) returns (stream HealthCheckResponse)`: This method is implemented but returns an `Unimplemented` status.

## Services it depends on
*   **Google Cloud Secret Manager**:
    *   **How**: gRPC (via `cloud.google.com/go/secretmanager` client library).
    *   **Why**: Used to retrieve sensitive information, specifically the PostgreSQL password for AlloyDB database access, if configured to load the catalog from AlloyDB.
*   **AlloyDB**:
    *   **How**: Direct database connection using `github.com/jackc/pgx/v5/pgxpool` and `cloud.google.com/go/alloydbconn` for secure connection.
    *   **Why**: Can be configured to load the product catalog data from an AlloyDB PostgreSQL-compatible database instead of a local file, based on environment variables like `ALLOYDB_CLUSTER_NAME`.
*   **OpenTelemetry Collector / Tracing service**:
    *   **How**: gRPC (via `go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc`).
    *   **Why**: Exports trace data for distributed tracing if the `ENABLE_TRACING` environment variable is set. The collector address is configured via `COLLECTOR_SERVICE_ADDR`.

## Core functionalities
*   **Product Catalog Management**: Provides methods to list, retrieve, and search products.
*   **Data Source Flexibility**: Supports loading product data from either a local `products.json` file or an external AlloyDB database.
*   **Health Checking**: Implements standard gRPC health checks to report service status.
*   **Dynamic Catalog Reloading**: Allows reloading the product catalog data without restarting the service, triggered by OS signals.
*   **Trace Context Propagation**: Integrates with OpenTelemetry for distributed tracing and context propagation.

## Notable dependencies
*   `cloud.google.com/go/alloydbconn`: For connecting to Google Cloud AlloyDB instances.
*   `cloud.google.com/go/secretmanager`: For accessing secrets stored in Google Cloud Secret Manager.
*   `cloud.google.com/go/profiler`: For integrating with Google Cloud Profiler for performance analysis.
*   `github.com/jackc/pgx/v5`: A PostgreSQL driver for Go, used for database interactions with AlloyDB.
*   `github.com/sirupsen/logrus`: A structured logging library for Go.
*   `go.opentelemetry.io/contrib/instrumentation/google.golang.org/grpc/otelgrpc`: OpenTelemetry instrumentation for gRPC, enabling tracing of RPC calls.
*   `go.opentelemetry.io/otel`: The OpenTelemetry API for Go.
*   `google.golang.org/grpc`: The official gRPC framework for Go.

## Anything unusual
The service includes a "dynamic catalog reloading" feature which, as noted in its `README.md`, is "purposefully not well implemented" and acts as a "bugged" feature. When enabled (via a `USR1` signal), the catalog is reloaded on *every* request, leading to significant performance degradation, consuming "more than 80% of the CPU time" in the `parseCatalog` function. Additionally, an `EXTRA_LATENCY` environment variable allows injecting artificial delays into every API call.