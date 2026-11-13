define internal i64 @mime.w3(i64 %w0) {
  %v0 = mul i64 %w0, %w0
  ret i64 %v0
}

define internal i64 @mime.w4(i64 %w0) {
  %v0 = sub i64 %w0, 1
  ret i64 %v0
}

define internal i64 @mime.w5(i64 %w0) {
  %v0 = sub i64 0, %w0
  ret i64 %v0
}

define internal i64 @mime.w6(i64 %w0) {
  %v0 = add i64 %w0, -9223372036854775808
  ret i64 %v0
}

define internal i64 @mime.w7(i64 %w1, i64 %w2) {
  %v0 = sub i64 %w1, %w2
  ret i64 %v0
}

define internal i64 @mime.w8() {
  ret i64 7
}
