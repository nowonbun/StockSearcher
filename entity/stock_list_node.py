from dataclasses import dataclass


@dataclass
class StockListNode:
    b: int
    code: str
    name: str
    stocktype: str
    industry33code: str
    industry33type: str
    industry17code: str
    industry17type: str
    scalecode: str
    scaletype: str

    def __getitem__(self, key):
        return getattr(self, key)


def generateSqlQuery(nodes: list[StockListNode]) -> str:
    column = [
        "code",
        "name",
        "stocktype",
        "industry33code",
        "industry33type",
        "industry17code",
        "industry17type",
        "scalecode",
        "scaletype",
    ]
    query = "INSERT INTO STOCK_LIST ("
    query += ", ".join([f"{v}" for v in column])
    query += ",create_date, update_date"
    query += ") VALUES "
    comma = ""
    query += ", ".join(
        " ( " + ", ".join([f"'{node[v]}'" for v in column]) + ",now(), now()) "
        for node in nodes
    )
    query += " ON DUPLICATE KEY UPDATE "
    query += ", ".join([f"{v} = VALUES({v})" for v in column])
    query += ", update_date = now() "
    return query
