# Distributed Systems Practice - Art With Drones
This project contains the code and documentation developed for the distributed systems practice assignment at the University of Alicante during the 2023-2024 academic year.

## Overview
The goal of this practice was to implement a distributed drone light show system where various components communicate over REST APIs while incorporating security features like authentication, encryption and auditing.

This was done according to the guidelines and requirements specified by the university for the assignment.

## Implementation
The key components implemented are:

AD_Engine: Consumes weather data from OpenWeatherMap API, implements token-based drone authentication.
AD_Registry: Exposes REST API for drone registration and token management.
Drones: Connect via REST API, authenticate securely with registry.
AD_Engine API: Exposes REST API for frontend to access drone/map state.
Frontend: Single page app to display map/drones by consuming engine API.
Encryption: Encrypted communication channels using symmetric encryption and Hybrid with RSA and AES.
Auditing: Logs all events to file in structured format with metadata.
