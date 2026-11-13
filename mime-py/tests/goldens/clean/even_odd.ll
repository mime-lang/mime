define i1 @even(i64 %w0) {
entry:
  %v0 = icmp eq i64 %w0, 0
  br i1 %v0, label %b0, label %b1
b0:
  ret i1 true
b1:
  %v1 = sub i64 %w0, 1
  %v2 = call i1 @odd(i64 %v1)
  ret i1 %v2
}

define i1 @odd(i64 %w0) {
entry:
  %v0 = icmp eq i64 %w0, 0
  br i1 %v0, label %b0, label %b1
b0:
  ret i1 false
b1:
  %v1 = sub i64 %w0, 1
  %v2 = call i1 @even(i64 %v1)
  ret i1 %v2
}
