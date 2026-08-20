# ADR 0001: Store field names, never values

Status: accepted.

ContractGraph needs evidence about which parts of a response consumers use, but does not need customer data. The collector therefore accepts an explicit `contract.fields` sketch and discards all other payload content. This reduces breach impact and makes accidental sensitive-value retention testable.
