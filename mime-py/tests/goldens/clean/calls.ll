define internal i64 @mime.w5(i64 %w0) {
  %v0 = add i64 %w0, %w0
  ret i64 %v0
}

define internal i64 @mime.w6(i64 %w1, i64 %w2) {
  %v0 = sub i64 %w1, %w2
  ret i64 %v0
}

define internal i64 @mime.w7() {
  ret i64 10
}

define internal i1 @mime.w8(i64 %w0) {
  %v0 = icmp slt i64 %w0, 0
  ret i1 %v0
}

define i64 @quadruple(i64 %w3) {
  %v0 = call i64 @mime.w5(i64 %w3)
  %v1 = call i64 @mime.w5(i64 %v0)
  %v2 = call i64 @mime.w7()
  %v3 = call i64 @mime.w6(i64 %v1, i64 %v2)
  ret i64 %v3
}

define i64 @magnitude(i64 %w0) {
entry:
  %v0 = call i1 @mime.w8(i64 %w0)
  br i1 %v0, label %b0, label %b1
b0:
  %v1 = call i64 @mime.w6(i64 0, i64 %w0)
  ret i64 %v1
b1:
  ret i64 %w0
}
