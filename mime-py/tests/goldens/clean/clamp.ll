define i64 @"mime.clamp"(i64 %"@x", i64 %"@lo", i64 %"@hi") {
entry:
  %"%below" = icmp slt i64 %"@x", %"@lo"
  br i1 %"%below", label %"e0.0", label %"e0.1"
"e0.0":
  br label %"^low"
"e0.1":
  br label %"^check"
"^check":
  %"^check%above" = icmp sgt i64 %"@x", %"@hi"
  br i1 %"^check%above", label %"e1.0", label %"e1.1"
"e1.0":
  br label %"^high"
"e1.1":
  br label %"^keep"
"^low":
  ret i64 %"@lo"
"^high":
  ret i64 %"@hi"
"^keep":
  ret i64 %"@x"
}
