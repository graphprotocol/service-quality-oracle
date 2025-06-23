
---

# Upcoming Eligibility Criteria

**We will announce changes to the eligibility criteria in the table below.** Once the change goes live, it will be reflected in the `Active Eligibility Criteria` section of this document.

| Upcoming Requirement | Justification | Date Requirement Will Be Updated/Introduced (YYYY-MM-DD) |
|----------------------|---------------|----------------------------------------------------------|
| **Example Requirement:** | This is a placeholder for future criteria. Watch this space to stay informed. We will also announce upcoming requirements via official channels. | `YYYY-MM-DD` |

> **Note**:
> We will typically allow a 14 day window after announcing a change before it goes live.

---

# Active Eligibility Criteria

The following criteria is used to identify indexers that should be eligible to receive indexing rewards.

- **Days Online Requirement:** Indexers must be online for **5+ days** in a given **28 day** rolling period for rewards eligibility.
- **Daily Query Requirement:** To be online, an indexer must serve at least **1 qualifying query** on **10 different subgraphs**.
- **Query Quality Requirements:** A qualifying query is one that simutanousely meets **all** of the following criteria:
  - Query Response HTTP Status: **200 OK**.
  - Query Response Latency: **< 5,000 ms**.
  - Query Freshness: **< 50,000 blocks** behind chainhead.
  - Subgraph Curation Signal: **≥ 500 GRT**.

Eligibility for indexing rewards is typically refreshed daily via the ServiceQualityOracle contract.

> **Note**:
> Once an indexer has successfully qualified for issuance by satisfying all of the above criteria, and a corresponding transaction has been submitted on chain by an authorized Oracle into the ServiceQualityOracle contract, the now eligible indexer can continue claiming indexing rewards from the protocol for the duration of the qualification period (default is 14 days), even if issuance eligibility requirements change.

---

# Eligibility Requirements Changelog

This table tracks changes to eligibility requirements over time.

| Requirement Category | Requirement Details | Effective Date (YYYY-MM-DD) | Change Type | Justification | Notes |
|----------------------|---------------------|-----------------------------|-------------|---------------|-------|
| **Days Online** | Indexers must be online for **5+ days** in a given **28 day** rolling period for rewards eligibility. | TBD | Initial | Encourages indexers familiarize themselves with infrastructure maintainance and ongoing operations. | Planned for Service Quality Oracle launch |
| **Daily Query Requirement** | Must serve **≥1 qualifying query** on **≥10 different subgraphs** per day for a day to count towards the online requirement. | TBD | Initial | Encourages indexers to become familiar with the process of syncing a range of subgraphs. | Planned for Service Quality Oracle launch |
| **Query Quality Requirements** | *•* Query Response HTTP Status: **200 OK**<br>*•* Query Response Latency: **< 5,000 ms**<br>*•* Query Freshness: **< 50,000 blocks** behind chainhead.<br>*•* Subgraph Curation Signal: **≥ 500 GRT**. | TBD | Initial | *•* Indexer infrastructure needs to serve successful queries to benefit data consumers.<br>*•* Fast query responses are important to data consumers.<br>*•* Encourages indexers to sync to chainhead.<br>*•* Creates a barrier against gaming eligibility requirements. | Planned for Service Quality Oracle launch |

---

# Future Example Changes

The following are examples of how future changes would be recorded in the changelog above:

| Requirement Category | Requirement Details | Effective Date (YYYY-MM-DD) | Change Type | Justification | Notes |
|----------------------|---------------------|------------------------------|------------|---------------|-------|
| **Days Online** | Must be online for **10+ days** in a **28 day** rolling period | YYYY-MM-DD | Updated | Increase reliability requirements based on network maturity | Increased from 5+ days |
| **Query Latency** | Query response latency must be **< 1,000 ms** | YYYY-MM-DD | Updated | Improve user experience with faster responses | Tightened from < 5,000 ms |
| **Indexer Stake** | Indexer must have **≥ 100,000 GRT** staked | YYYY-MM-DD | New | Ensure indexers have skin in the game for quality service | New requirement added |

---
