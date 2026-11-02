import streamlit as st
from sqlalchemy import text
from datetime import datetime
from pytz import timezone

# secrets.toml 의 [connections.neon] url 사용
conn = st.connection("neon", type="sql")
seoul = timezone("Asia/Seoul")

st.title("마당 서점 관리 시스템")

# 고객/도서 목록 (5분 캐시)
cust_df = conn.query("SELECT custid, name FROM Customer ORDER BY custid;", ttl=300)
book_df = conn.query("SELECT bookid, bookname FROM Book ORDER BY bookid;", ttl=300)

customers = ["고객선택"] + cust_df["name"].tolist()
books = [f"{r.bookid}.{r.bookname}" for r in book_df.itertuples()]

tab1, tab2 = st.tabs(["고객조회", "거래 입력"])

name = tab1.selectbox("고객명", customers)

if name != "고객선택":
    # 고객번호는 Customer 테이블에서 가져옴 → 거래 내역이 없는 고객도 주문 가능
    custid = int(cust_df.loc[cust_df["name"] == name, "custid"].iloc[0])

    # Supabase rpc('get_transactions_by_name') 대신 JOIN 쿼리
    result = conn.query(
        """
        SELECT c.custid, c.name, b.bookname, o.orderdate, o.saleprice
        FROM Customer c
        JOIN Orders o ON c.custid = o.custid
        JOIN Book   b ON o.bookid = b.bookid
        WHERE c.name = :name
        ORDER BY o.orderdate;
        """,
        params={"name": name},
        ttl=0,  # 거래 입력 직후 바로 보이도록 캐시 안 함
    )

    if result.empty:
        tab1.write("거래 내역이 없습니다.")
    else:
        tab1.dataframe(result, hide_index=True)

    # ---- 거래 입력 ----
    tab2.write(f"고객번호: {custid}")
    tab2.write(f"고객명: {name}")
    select_book = tab2.selectbox("구매 서적:", books)
    price = tab2.number_input("금액", min_value=0, step=1000)

    if tab2.button("거래 입력"):
        bookid = int(select_book.split(".")[0])
        dt = datetime.now(seoul).strftime("%Y-%m-%d")

        with conn.session as s:
            # orderid 계산과 INSERT 를 한 문장으로 → 조회/입력 사이 끼어들기 방지
            s.execute(
                text("""
                    INSERT INTO Orders (orderid, custid, bookid, saleprice, orderdate)
                    SELECT COALESCE(MAX(orderid), 0) + 1, :custid, :bookid, :price, :dt
                    FROM Orders;
                """),
                {"custid": custid, "bookid": bookid, "price": int(price), "dt": dt},
            )
            s.commit()

        tab2.success("거래가 입력되었습니다.")
        st.rerun()