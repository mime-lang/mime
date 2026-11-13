define i64 @gcd(i64 %w0, i64 %w1) {
entry:
  br label %b0
b0:
  %v0 = phi i64 [ %w0, %entry ], [ %v1, %b2.d0 ]
  %v1 = phi i64 [ %w1, %entry ], [ %v3, %b2.d0 ]
  %v2 = icmp eq i64 %v1, 0
  br i1 %v2, label %b1, label %b2
b2:
  %v3.zero = icmp eq i64 %v1, 0
  br i1 %v3.zero, label %b2.t0, label %b2.d0
b2.t0:
  call void @mime.trap(i64 0)
  unreachable
b2.d0:
  %v3.min = icmp eq i64 %v0, -9223372036854775808
  %v3.neg = icmp eq i64 %v1, -1
  %v3.edge = and i1 %v3.min, %v3.neg
  %v3.by = select i1 %v3.edge, i64 1, i64 %v1
  %v3 = srem i64 %v0, %v3.by
  br label %b0
b1:
  ret i64 %v0
}

define i64 @gcd_by_recursion(i64 %w0, i64 %w1) {
entry:
  %v0 = icmp eq i64 %w1, 0
  br i1 %v0, label %b0, label %b1
b0:
  ret i64 %w0
b1:
  %v1.zero = icmp eq i64 %w1, 0
  br i1 %v1.zero, label %b1.t0, label %b1.d0
b1.t0:
  call void @mime.trap(i64 1)
  unreachable
b1.d0:
  %v1.min = icmp eq i64 %w0, -9223372036854775808
  %v1.neg = icmp eq i64 %w1, -1
  %v1.edge = and i1 %v1.min, %v1.neg
  %v1.by = select i1 %v1.edge, i64 1, i64 %w1
  %v1 = srem i64 %w0, %v1.by
  %v2 = call i64 @gcd_by_recursion(i64 %w1, i64 %v1)
  ret i64 %v2
}

declare void @mime.trap(i64) noreturn
