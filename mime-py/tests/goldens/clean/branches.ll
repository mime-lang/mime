define i64 @"mime.sum"(i64 %"@n") {
entry:
  br label %"e0.0"
"e0.0":
  br label %"^loop"
"^loop":
  %"^loop%i" = phi i64 [ 0, %"e0.0" ], [ %"^loop%next", %"e1.1" ]
  %"^loop%total" = phi i64 [ 0, %"e0.0" ], [ %"^loop%more", %"e1.1" ]
  %"^loop%limit" = phi i64 [ %"@n", %"e0.0" ], [ %"^loop%limit", %"e1.1" ]
  %"^loop%done" = icmp sgt i64 %"^loop%i", %"^loop%limit"
  %"^loop%next" = add i64 %"^loop%i", 1
  %"^loop%more" = add i64 %"^loop%total", %"^loop%i"
  br i1 %"^loop%done", label %"e1.0", label %"e1.1"
"e1.0":
  br label %"^end"
"e1.1":
  br label %"^loop"
"^end":
  %"^end%result" = phi i64 [ %"^loop%total", %"e1.0" ]
  ret i64 %"^end%result"
}

define i1 @"mime.positive"(i64 %"@n") {
entry:
  %"%yes" = icmp sgt i64 %"@n", 0
  ret i1 %"%yes"
}

define i64 @"mime.pick"(i1 %"@flag") {
entry:
  br i1 %"@flag", label %"e0.0", label %"e0.1"
"e0.0":
  br label %"^out"
"e0.1":
  br label %"^out"
"^out":
  %"^out%v" = phi i64 [ 1, %"e0.0" ], [ 2, %"e0.1" ]
  ret i64 %"^out%v"
}

define i1 @"mime.negate"(i1 %"@flag") {
entry:
  br i1 %"@flag", label %"e0.0", label %"e0.1"
"e0.0":
  br label %"^out"
"e0.1":
  br label %"^out"
"^out":
  %"^out%v" = phi i1 [ false, %"e0.0" ], [ true, %"e0.1" ]
  ret i1 %"^out%v"
}
