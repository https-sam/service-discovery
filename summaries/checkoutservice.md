# checkoutservice

## Overview
The checkoutservice is a core component responsible for orchestrating the final steps of a customer's purchase journey. It processes user checkout requests by interacting with various other microservices to gather cart items, calculate costs, handle payments, manage shipping, and send order confirmations. Its primary role is to bundle these operations into a single `PlaceOrder` transaction.

## Language & framework
This service is implemented in **Go** (version 1.25.0, with toolchain go1.26.1) and leverages **gRPC** for inter-service communication and exposing its own API.

## APIs exposed
The `checkoutservice` exposes the following gRPC methods:

*   **`CheckoutService/PlaceOrder`**: Processes a complete order request, taking user ID, currency, shipping address, email, and credit card information, and returns the order result.
*   **`Health/Check`**: Provides a standard gRPC health check to indicate if the service is operational.
*   **`Health/Watch`**: This method is part of the gRPC Health Checking Protocol but is explicitly not implemented, returning `codes.Unimplemented`.

## Services it depends on
The `checkoutservice` acts as an orchestrator, depending on several other services via gRPC:

*   **`CartService` (gRPC)**:
    *   To `GetCart` items for a given user during the order preparation.
    *   To `EmptyCart` after a successful order placement.
*   **`ProductCatalogService` (gRPC)**:
    *   To `GetProduct` details for each item in the cart to determine individual product costs.
*   **`ShippingService` (gRPC)**:
    *   To `GetQuote` for shipping costs based on the address and cart items.
    *   To `ShipOrder` once the payment is processed, initiating the physical shipment.
*   **`CurrencyService` (gRPC)**:
    *   To `Convert` prices (e.g., product prices, shipping costs) from their base currency (USD) to the user's selected currency.
*   **`PaymentService` (gRPC)**:
    *   To `Charge` the user's credit card for the total order amount.
*   **`EmailService` (gRPC)**:
    *   To `SendOrderConfirmation` to the user after a successful order.
*   **`COLLECTOR_SERVICE_ADDR` (gRPC)**: This service is used for OpenTelemetry tracing, specifically to export traces via OTLP over gRPC.

## Core functionalities
*   **Order Placement**: Handles the end-to-end process of placing an order.
*   **Cart Retrieval and Processing**: Fetches the user's cart, prepares order items with localized pricing.
*   **Shipping Cost Calculation**: Obtains a shipping quote and converts it to the user's currency.
*   **Payment Processing**: Charges the user's credit card for the total order amount.
*   **Order Fulfillment Initiation**: Triggers the shipping process by calling the shipping service.
*   **Cart Management**: Empties the user's cart upon successful order completion.
*   **Order Confirmation**: Sends an order confirmation email to the user.
*   **Health Checking**: Responds to standard gRPC health checks.

## Notable dependencies
*   `cloud.google.com/go/profiler`: For Stackdriver Profiler integration.
*   `github.com/google/uuid`: For generating unique order IDs.
*   `github.com/pkg/errors`: Provides simple error handling primitives.
*   `github.com/sirupsen/logrus`: A structured, pluggable logging facility.
*   `go.opentelemetry.io/contrib/instrumentation/google.golang.org/grpc/otelgrpc`: For OpenTelemetry tracing integration with gRPC.
*   `go.opentelemetry.io/otel`, `go.opentelemetry.io/otel/sdk`: Core OpenTelemetry libraries for tracing.
*   `go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc`: OpenTelemetry exporter for sending traces via gRPC.
*   `google.golang.org/grpc`: The main gRPC framework.
*   `google.golang.org/protobuf`: Protocol Buffers implementation for Go.

## Anything unusual
The service includes a custom `money` package (`src/checkoutservice/money/money.go`) that provides functions for handling monetary values (addition, multiplication, validation, negation) using a custom `pb.Money` struct. This suggests a bespoke solution for precise financial calculations rather than relying on standard floating-point arithmetic or a third-party money library. Additionally, the proto generation script `genproto.sh` uses `go_out` and `go-grpc_out` flags with `paths=source_relative`, which is a specific way to organize generated Go code relative to the `.proto` files.