# Bookswagon-bot
Customer Support
select distinct top 10* from view_bw where OrderStatus = 'processed';
select *from Table_OrderCancellationReason
select top 3 * from Table_OrderSummary where Order_Number= 'BW17082501421959';
select * from View_GetOrderDetailListUpdatedNew where order_number = 'BW17082501421959';
create view view_bw 
as
SELECT distinct  top 1000
    v1.Order_Number,
    os.ID_OrderSummary,
    v2.Product_Title,
    v2.ISBN13,
    v1.showOrderDate,
    v1.DueDate,
    v1.OrderStatus,
	oc.Reason,
    v1.PaymentStatus,
    v1.amount,
    v1.customer_Email,
    v1.Customer_Name,
    sa.Shipping_Address,
    sa.Shipping_City,
    sa.Shipping_Country,
    sa.Shipping_State,
    sa.Shipping_Zip,
    sa.Shipping_Mobile,
    sa.Tracking_Number
FROM View_GetOrderDetailListUpdatedNew v1
JOIN Table_OrderSummary os ON v1.Order_Number = os.Order_Number
full Join Table_OrderCancellationReason oc on os.ID_CancellationReason = oc.ID_OrderCancellationReason
JOIN Table_OrderShippingAddress sa ON os.ID_OrderSummary = sa.ID_OrderSummary
OUTER APPLY (
    SELECT distinct Product_Title,ISBN13
    FROM View_Order_Customer_Product v2
    WHERE v2.Order_Number = v1.Order_Number
) v2;
