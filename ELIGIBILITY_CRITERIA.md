
---
# Upcoming Eligibility Criteria

**We will announce changes to the eligibility criteria in the table below.** Once the change goes live, it will be reflected in the `Active Eligibility Criteria` section of this document.

| Upcoming Requirement | Justification | Date Requirement Will Be Updated/Introduced (YYYY-MM-DD) |
|----------------------|---------------|----------------------------------------------------------|
| **Example Requirement:** | This is a placeholder for future criteria. Watch this space to stay informed. We will also announce any upcoming requirements via our existing official channels. | `YYYY-MM-DD` |

> **Note**:
> When announcing new eligibility criteria we will allow a window for indexers to prepare their infrastructure before any new/updated criteria goes live, refer to the `Date Requirement Will Be Updated/Introduced (YYYY-MM-DD)` column to see when an upcoming eligibility criterion will take effect. We will typically allow a 14-day window after announcing a change before it goes live.

---
# Active Eligibility Criteria

The Service Quality Oracle determines which indexers are eligible to receive indexing rewards using a threshold rewards algorithm that operates by checking indexers meet the following criteria:

1. **Indexers must be online for 5+ days in a given 28 day rolling period.**
    1. **To be online, an indexer must serve at least 1 qualifying query on 10 different subgraphs**
        1. **A qualifying query is one where:**
            1. **The query response HTTP status was 200 OK, indicating query success.**
            2. **The query response latency was <5,000 ms.**
            3. **The query was served <50,000 blocks behind chainhead.**
            4. **The subgraph had at least 500 GRT in curation signal at the time that the query was served.**

All four qualifying query criteria must be satisfied simultaneously for a query to count towards the daily requirement.
As above, the qualifying query criteria must be satisfied on 10+ subgraphs per day, for 5+ days in any given 28 day rolling window.
Eligibility for indexing rewards is typically refreshed daily via the ServiceQualityOracle contract.

> **Note**:
> * Once an indexer has successfully qualified for issuance by satisfying the above criteria, and a corresponding transaction has been placed on chain by an authorizde Oracle into the ServiceQualityOracle contract, the now eligible indexer can continue claiming indexing rewards from the protocol for the duration of the qualification period (default is 14 days), even if the issuance eligibility requirements change thereafter.

---


#### Below is a table showing Justification, date and notes for the above eligibility criteria 

| Requirement | Justification | Date That Requirement Was Last Updated/Introduced (YYYY-MM-DD) | Notes |
|-------------|---------------|----------------------------------------------------------------|-------|
| **Query Status:** The query must have a `200 OK` HTTP response status indicating query success | Indexer infrastructure needs to be capable of serving successful queries to benefit data consumers. | TBD | This requirement is planned to be introduced at launch of the Service Quality Oracle |
| **Query Latency:** The query response must be delivered to the gateway in `< 5,000 ms` | Fast query responses are important to data consumers. | TBD | This requirement is planned to be introduced at launch of the Service Quality Oracle |
| **Query Freshness:** The query must be served from a subgraph that is `< 50,000 blocks` behind chainhead | Data needs to be fresh to be useful to data consumers. | TBD | This requirement is planned to be introduced at launch of the Service Quality Oracle |
| **Subgraph Signal:** The subgraph needs to have `≥ 500 GRT` in curation signal at the time when the query was served. | Indexers are encouraged to serve data on subgraphs that have curation signal. This also creates an economic barrier against those that prefer to game the system. | TBD | This requirement is planned to be introduced at launch of the Service Quality Oracle |
