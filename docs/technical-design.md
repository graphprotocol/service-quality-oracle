# Technical Design & Architecture

This document outlines key architectural decisions and data flows within the Service Quality Oracle.

## RPC Provider Failover and Circuit Breaker Logic

The application is designed to be resilient to transient network issues and RPC provider failures. It uses a multi-layered approach involving internal retries, provider rotation, and an application-level circuit breaker to prevent catastrophic failures and infinite restart loops.

The following diagram illustrates the sequence of events when all RPC providers fail, leading to a single recorded failure by the circuit breaker.

```mermaid
sequenceDiagram
    participant main as Main Oracle
    participant client as BlockchainClient
    participant circuit_breaker as CircuitBreaker
    participant slack as SlackNotifier

    main->>client: batch_allow_indexers_issuance_eligibility()
    activate client

    alt RPC Loop (for each provider)
        client->>client: _execute_rpc_call() with provider A
        note right of client: Fails after 5 retries
        client-->>client: raises ConnectionError

        note right of client: Catches error, logs rotation
        
        client->>client: _execute_rpc_call() with provider B
        note right of client: Fails after 5 retries
        client-->>client: raises ConnectionError

        note right of client: All providers tried and failed
    end
    
    client-->>main: raises Final ConnectionError
    deactivate client

    main->>circuit_breaker: record_failure()
    main->>slack: send_failure_notification()
    note right of main: sys.exit(1) causes Docker restart
``` 