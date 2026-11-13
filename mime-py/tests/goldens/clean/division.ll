define i64 @quotient(i64 %w0, i64 %w1) {
  %v0.zero = icmp eq i64 %w1, 0
  br i1 %v0.zero, label %entry.t0, label %entry.d0
entry.t0:
  call void @mime.trap(i64 0)
  unreachable
entry.d0:
  %v0.min = icmp eq i64 %w0, -9223372036854775808
  %v0.neg = icmp eq i64 %w1, -1
  %v0.over = and i1 %v0.min, %v0.neg
  br i1 %v0.over, label %entry.t1, label %entry.d1
entry.t1:
  call void @mime.trap(i64 1)
  unreachable
entry.d1:
  %v0 = sdiv i64 %w0, %w1
  ret i64 %v0
}

define i64 @remainder(i64 %w0, i64 %w1) {
  %v0.zero = icmp eq i64 %w1, 0
  br i1 %v0.zero, label %entry.t0, label %entry.d0
entry.t0:
  call void @mime.trap(i64 2)
  unreachable
entry.d0:
  %v0.min = icmp eq i64 %w0, -9223372036854775808
  %v0.neg = icmp eq i64 %w1, -1
  %v0.over = and i1 %v0.min, %v0.neg
  br i1 %v0.over, label %entry.t1, label %entry.d1
entry.t1:
  call void @mime.trap(i64 3)
  unreachable
entry.d1:
  %v0 = srem i64 %w0, %w1
  ret i64 %v0
}

define i64 @unsigned_quotient(i64 %w0, i64 %w1) {
  %v0.zero = icmp eq i64 %w1, 0
  br i1 %v0.zero, label %entry.t0, label %entry.d0
entry.t0:
  call void @mime.trap(i64 4)
  unreachable
entry.d0:
  %v0 = udiv i64 %w0, %w1
  ret i64 %v0
}

define i64 @unsigned_remainder(i64 %w0, i64 %w1) {
  %v0.zero = icmp eq i64 %w1, 0
  br i1 %v0.zero, label %entry.t0, label %entry.d0
entry.t0:
  call void @mime.trap(i64 5)
  unreachable
entry.d0:
  %v0 = urem i64 %w0, %w1
  ret i64 %v0
}

define i1 @both(i1 %w6, i1 %w7) {
  %v0 = and i1 %w6, %w7
  ret i1 %v0
}

define i1 @either(i1 %w6, i1 %w7) {
  %v0 = or i1 %w6, %w7
  ret i1 %v0
}

define i1 @one_of(i1 %w6, i1 %w7) {
  %v0 = xor i1 %w6, %w7
  ret i1 %v0
}

define i1 @negation(i1 %w6) {
  %v0 = xor i1 %w6, true
  ret i1 %v0
}

declare void @mime.trap(i64) noreturn
