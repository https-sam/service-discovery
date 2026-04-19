## Overview

The Ad service is a Java microservice responsible for providing advertisements to users. Its primary role in the wider system is to serve ads based on contextual keywords provided in a request, or to return random ads if no context is given or no specific ads match. This service is part of the `hipstershop` e-commerce demo application.

## Language & framework

The Ad service is primarily written in Java. It uses gRPC for inter-service communication and Gradle as its build automation tool. The service leverages the Eclipse Temurin JDK for its runtime environment.

## APIs exposed

The Ad service exposes the following gRPC APIs:

*   **`AdService`**
    *   `rpc GetAds(AdRequest) returns (AdResponse)`: Retrieves a list of ads based on a set of context keywords. If no context is provided or no matching ads are found, it returns random ads.
*   **`Health`**
    *   `rpc Check(HealthCheckRequest) returns (HealthCheckResponse)`: Standard gRPC health check endpoint to determine if the service is serving requests.

## Services it depends on

Not evident from the provided files. The `AdService` implementation does not contain any client-side calls to other `hipstershop` services.

## Core functionalities

*   **Advertisement Retrieval**: Serves ads to calling clients.
*   **Contextual Advertising**: Retrieves ads by matching provided `context_keys` (e.g., product categories) to a predefined internal mapping.
*   **Random Advertising**: If no context keys are provided, or if no ads match the given context, the service returns a fixed number of random ads.
*   **Health Checking**: Responds to gRPC health check requests.

## Notable dependencies

*   **gRPC Libraries**: `io.grpc:grpc-protobuf`, `io.grpc:grpc-stub`, `io.grpc:grpc-netty`, `io.grpc:grpc-services`, `io.grpc:grpc-census` for building and serving gRPC services.
*   **Protocol Buffers**: `com.google.protobuf:protobuf-java` for data serialization and deserialization.
*   **Logging**: `org.apache.logging.log4j` for application logging, configured to output JSON for Stackdriver integration.
*   **Guava**: `com.google.common.collect.ImmutableListMultimap` and `com.google.common.collect.ImmutableMap` for efficient immutable collections, used to store and manage the ad data.
*   **Netty**: `io.netty:netty-tcnative-boringssl-static` for underlying network communication.

## Anything unusual

The ad content and their associated categories (`clothing`, `accessories`, `footwear`, `hair`, `decor`, `kitchen`) are hardcoded directly within the `AdService.java` file in a static `ImmutableListMultimap`. This suggests that the ad data is not fetched dynamically from a database or external configuration, but is compiled directly into the service. Additionally, there are commented-out sections and `@TODO` items in both the `Dockerfile` and `AdService.java` related to Stackdriver Profiler and OpenTelemetry tracing, indicating that these observability features are planned or were partially implemented but are currently disabled or temporarily unavailable.