## Overview
This service acts as an AI-powered shopping assistant. It takes a user's prompt and an image of a room, then uses Google's Generative AI (Gemini) to describe the room's style. It subsequently performs a vector similarity search in an AlloyDB PostgreSQL database to find relevant products from a catalog, finally generating tailored product recommendations based on the user's request, the room's style, and the retrieved products.

## Language & framework
The service is primarily written in Python and uses the Flask web framework to expose its API.

## APIs exposed
The service exposes a single HTTP POST endpoint:
*   `/` (POST): Accepts a JSON payload containing a `message` (user prompt, potentially URL-encoded) and an `image` URL. It returns generated product recommendations.

## Services it depends on
*   **Google Secret Manager**: Via `google.cloud.secretmanager_v1` (gRPC/HTTP) to securely retrieve the PostgreSQL password for AlloyDB.
*   **Google Generative AI (Gemini)**: Via `langchain-google-genai` (API) to perform two main tasks:
    1.  Image analysis (using `gemini-1.5-flash` with vision capabilities) to describe the style of a room from an image.
    2.  Text generation (using `gemini-1.5-flash`) to formulate product recommendations based on a prompt and retrieved product information.
*   **AlloyDB PostgreSQL**: Via `langchain-google-alloydb-pg` (database connection) to connect to a PostgreSQL database instance. This database is used as a vector store to perform similarity searches for product recommendations.

## Core functionalities
*   Receiving a user's shopping request along with an image of a room.
*   Analyzing the provided image using a large language model (Gemini Vision Pro) to extract a detailed description of the room's style.
*   Performing a vector similarity search within an AlloyDB PostgreSQL database to find products relevant to both the user's request and the detected room style.
*   Generating personalized product recommendations using a large language model (Gemini Pro), incorporating the room description, user prompt, and details of the most relevant products from the catalog.
*   Extracting and listing product IDs for the top recommendations.

## Notable dependencies
*   `flask`: Web framework for handling HTTP requests.
*   `langchain`: Core library for building LLM applications.
*   `langchain-google-genai`: Integrates with Google's Generative AI models (Gemini) for text generation and image analysis.
*   `langchain-google-alloydb-pg`: Provides connectivity and vector store capabilities for Google Cloud AlloyDB PostgreSQL.
*   `google-cloud-secret-manager`: Client library for accessing secrets stored in Google Cloud Secret Manager.
*   `pillow`: Python Imaging Library, typically used for image processing.

## Anything unusual
The service includes `demo.proto` and `grpc/health/v1/health.proto` files in its directory structure, which define gRPC services for other microservices in the demo repository (e.g., CartService, ProductCatalogService). However, the `shoppingassistantservice.py` code itself does not directly implement any of these gRPC services nor does it make calls to them. Its primary mode of external communication is via HTTP (for its own API), and calls to Google Cloud services (Secret Manager, Generative AI, AlloyDB) through their respective client libraries. The presence of these `.proto` files seems to be part of a broader repository-wide setup rather than indicating direct gRPC interaction for this specific service within the microservice ecosystem.The following documentation provides an overview of the `shoppingassistantservice` microservice.

## Overview
This service acts as an AI-powered shopping assistant. It takes a user's prompt and an image of a room, then uses Google's Generative AI (Gemini) to describe the room's style. It subsequently performs a vector similarity search in an AlloyDB PostgreSQL database to find relevant products from a catalog, finally generating tailored product recommendations based on the user's request, the room's style, and the retrieved products.

## Language & framework
The service is primarily written in Python and uses the Flask web framework to expose its API.

## APIs exposed
The service exposes a single HTTP POST endpoint:
*   `/` (POST): Accepts a JSON payload containing a `message` (user prompt, potentially URL-encoded) and an `image` URL. It returns generated product recommendations.

## Services it depends on
*   **Google Secret Manager**: Via `google.cloud.secretmanager_v1` (gRPC/HTTP) to securely retrieve the PostgreSQL password for AlloyDB.
*   **Google Generative AI (Gemini)**: Via `langchain-google-genai` (API) to perform two main tasks:
    1.  Image analysis (using `gemini-1.5-flash` with vision capabilities) to describe the style of a room from an image.
    2.  Text generation (using `gemini-1.5-flash`) to formulate product recommendations based on a prompt and retrieved product information.
*   **AlloyDB PostgreSQL**: Via `langchain-google-alloydb-pg` (database connection) to connect to a PostgreSQL database instance. This database is used as a vector store to perform similarity searches for product recommendations.

## Core functionalities
*   Receiving a user's shopping request along with an image of a room.
*   Analyzing the provided image using a large language model (Gemini Vision Pro) to extract a detailed description of the room's style.
*   Performing a vector similarity search within an AlloyDB PostgreSQL database to find products relevant to both the user's request and the detected room style.
*   Generating personalized product recommendations using a large language model (Gemini Pro), incorporating the room description, user prompt, and details of the most relevant products from the catalog.
*   Extracting and listing product IDs for the top recommendations.

## Notable dependencies
*   `flask`: Web framework for handling HTTP requests.
*   `langchain`: Core library for building LLM applications.
*   `langchain-google-genai`: Integrates with Google's Generative AI models (Gemini) for text generation and image analysis.
*   `langchain-google-alloydb-pg`: Provides connectivity and vector store capabilities for Google Cloud AlloyDB PostgreSQL.
*   `google-cloud-secret-manager`: Client library for accessing secrets stored in Google Cloud Secret Manager.
*   `pillow`: Python Imaging Library, likely used for image processing in the context of the vision model input.

## Anything unusual
The service includes `demo.proto` and `grpc/health/v1/health.proto` files in its directory structure, which define gRPC services for other microservices in the demo repository (e.g., CartService, ProductCatalogService). However, the `shoppingassistantservice.py` code itself does not directly implement any of these gRPC services nor does it make calls to them. Its primary mode of external communication is via HTTP (for its own API), and calls to Google Cloud services (Secret Manager, Generative AI, AlloyDB) through their respective client libraries. The presence of these `.proto` files seems to be part of a broader repository-wide setup rather than indicating direct gRPC interaction for this specific service within the microservice ecosystem.