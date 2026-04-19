## Overview

The `frontend` service is the web-facing entry point for the e-commerce application. It serves the HTML pages for the online boutique, including the homepage, product detail pages, shopping cart, and checkout flow. It acts as an API gateway or orchestrator, aggregating data from various backend microservices (like product catalog, cart, and currency services) to render the user interface and process user actions like adding items to a cart or placing an order.

## Language & framework

The service is written in **Go** (version 1.26.2 specified in the Dockerfile). It uses `github.com/gorilla/mux` for HTTP routing.

## APIs exposed

The service exposes the following HTTP endpoints:

-   `GET /`: Renders the home page.
-   `GET /product/{id}`: Renders a product detail page.
-   `GET /cart`: Renders the user's shopping cart.
-   `POST /cart`: Adds an item to the user's cart.
-   `POST /cart/empty`: Empties the user's cart.
-   `POST /cart/checkout`: Places an order.
-   `POST /setCurrency`: Sets the user's currency preference via a cookie.
-   `GET /logout`: Clears the user's session cookies.
-   `GET /assistant`: Renders the shopping assistant chatbot page.
-   `POST /bot`: Proxies chatbot messages to the shopping assistant service.
-   `GET /product-meta/{ids}`: Returns product metadata as JSON, used by the chatbot.
-   `GET /_healthz`: A health check endpoint.
-   `/static/*`: Serves static assets like CSS, JavaScript, and images.

## Services it depends on

The service communicates with numerous backend services:

-   **product-catalog-service**: via gRPC, to get the list of all products and details for a single product.
-   **currency-service**: via gRPC, to get the list of supported currencies and to convert product prices.
-   **cart-service**: via gRPC, to add items to a user's cart, get the contents of the cart, and empty the cart.
-   **recommendation-service**: via gRPC, to fetch product recommendations for display on product and cart pages.
-   **checkout-service**: via gRPC, to place an order.
-   **shipping-service**: via gRPC, to get a shipping cost quote for the items in the cart.
-   **ad-service**: via gRPC, to request and display contextual advertisements.
-   **shopping-assistant-service**: via HTTP, to power the chatbot functionality.
-   **packaging-service**: via HTTP, to optionally fetch product packaging dimensions (weight, width, etc.). This is explicitly noted as an optional demo service.
-   **collector-service**: via gRPC, to export OpenTelemetry tracing data.

## Core functionalities

-   Renders HTML templates for all user-facing pages (home, product, cart, order confirmation, chatbot).
-   Serves static assets like CSS, images, and icons.
-   Manages user sessions and currency preference using browser cookies.
-   Handles user actions such as viewing products, adding items to the cart, and placing an order.
-   Orchestrates calls to various backend microservices to gather data for page rendering.
-   Provides a chatbot interface that communicates with a shopping assistant backend.
-   Validates user input for forms like "add to cart" and "place order".

## Notable dependencies

-   `github.com/gorilla/mux`: An HTTP request router.
-   `google.golang.org/grpc`: The client library for making gRPC calls to backend services.
-   `go.opentelemetry.io/*`: A suite of libraries for OpenTelemetry instrumentation and tracing.
-   `cloud.google.com/go/profiler`: For integrating with Google Cloud Profiler.
-   `github.com/sirupsen/logrus`: A structured logging library.
-   `github.com/go-playground/validator/v10`: For validating incoming request data structures.
-   `cloud.google.com/go/compute/metadata`: To fetch instance metadata when running on Google Cloud.

## Anything unusual

The service contains a local `money` package with a function named `MultiplySlow`, which performs multiplication through repeated addition; this is likely for demonstration purposes. The service uses both gRPC (for most backends) and HTTP (for the `shopping-assistant` and optional `packaging` services) for downstream communication, highlighting a mixed-protocol architecture. It also includes a debug flag, `ENABLE_SINGLE_SHARED_SESSION`, to hardcode a session ID, which simplifies testing but is not intended for production use.