define internal i64 @mime.w1(i64 %w0) {
entry:
  br label %b0
b0:
  %v0 = phi i64 [ %w0, %entry ], [ %v2, %b0 ]
  %v1 = icmp slt i64 %v0, 10
  %v2 = mul i64 %v0, 2
  br i1 %v1, label %b0, label %b1
b1:
  ret i64 %v0
}

define internal i64 @mime.w2(i64 %w0) {
entry:
  %v0 = add i64 %w0, 1
  br label %b0
b0:
  br label %b1
b1:
  ret i64 %v0
}

define internal i64 @mime.w3(i64 %w0) {
entry:
  %v0 = add i64 %w0, 1
  br label %b0
b0:
  %v1 = phi i64 [ 0, %entry ], [ %v3, %b0 ]
  %v2 = icmp sgt i64 %v1, 100
  %v3 = add i64 %v1, %v0
  br i1 %v2, label %b1, label %b0
b1:
  ret i64 %v1
}

define internal i64 @mime.w4(i64 %w0) {
entry:
  %v0 = icmp eq i64 %w0, 0
  %v1 = add i64 %w0, 1
  %v2 = sub i64 %w0, 1
  br i1 %v0, label %entry.e0, label %entry.e1
entry.e0:
  br label %b0
entry.e1:
  br label %b0
b0:
  %v3 = phi i64 [ %v1, %entry.e0 ], [ %v2, %entry.e1 ]
  ret i64 %v3
}
