# Upcoming Eligibility Criteria

We will announce changes to the eligibility criteria in the table below. Once the change goes live then it will be reflected in the eligibility criteria section of this document.

| Upcoming Requirement | Justification | Date Updated/Introduced (YYYY-MM-DD)|
|----------------------|---------------|-------------------------------------|
| **Requirement 1:** | This is a placeholder for future criteria, watch this space to stay informed. We will also announce any upcoming requirements via our existing official channels. | YYYY-MM-DD |

> **Note**:
>
> When announcing new eligibility criteria we will allow a window for indexers to prepare their infrastructure before any new/updated criteria goes live, refer to the `Date Updated/Introduced (YYYY-MM-DD)` column to see when upcoming eligibility criteria will merge.

# Eligibility Criteria

The Service Quality Oracle determines which indexers are eligible to receive indexing rewards using a threshold rewards algorithm that operates by checking indexers meet the following criteria:

1. Indexers must be online for 5+ days in a given 28 day rolling period.
    1. To be online an indexer must serve at least 1 qualifying query on 10 different subgraphs
        1. A qualifying query is one where:
            1. The query response HTTP status was 200 OK, indicating query success.
            2. The query response latency was <5,000 ms.
            3. The query was served <50,000 blocks behind chainhead.
            4. The subgraph had at least 500 GRT in curation signal at the time that the query was served.

> **Note**:
> 
> All four quality criteria must be satisfied simultaneously for a query to count towards the daily requirement.
> 
> The above query criteria must be satisfied on 10+ subgraphs per day, for 5+ days in any given 28 day rolling window.
>
> Issuance eligibility is refreshed daily via the ServiceQualityOracle contract.
>
> Once an indexer has qualified for issuance via the ServiceQualityOracle contract, they can claim indexing rewards from the protocol for the duration of the qualification period (default is 14 days), even if the requirements change.



| Requirement | Justification | Date Updated/Introduced (YYYY-MM-DD)|
|-------------|---------------|-------------------------------------|
| **Query Status:** The query must have a `200 OK` HTTP response status indicating query success | Indexer infrastructure needs to be capable of serving successful queries to benefit data consumers. | TBD (at genesis of the SQO) |
| **Query Latency:** The query response must be delivered to the gateway in `< 5,000 ms` | Fast query responses are important to data consumers. | TBD (at genesis of the SQO) |
| **Query Freshness:** The query must be served from a subgraph that is `< 50,000 blocks` behind chainhead | Data needs to be fresh to be useful to data consumers. | TBD (at genesis of the SQO) |
| **Subgraph Signal:** The subgraph needs to have `≥ 500 GRT` in curation signal at the time when the query was served. | Indexers are encouraged to serve data on subgraphs that have curation signal. This also creates an economic barrier against those that prefer to game the system. | TBD (at genesis of the SQO) |
