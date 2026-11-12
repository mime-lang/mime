define i64 @"$square"(i64 %"$number") {
  %"$p" = mul i64 %"$number", %"$number"
  ret i64 %"$p"
}

define i64 @"$less"(i64 %"$number") {
  %"$d" = sub i64 %"$number", 1
  ret i64 %"$d"
}

define i64 @"$negate"(i64 %"$number") {
  %"$n" = sub i64 0, %"$number"
  ret i64 %"$n"
}

define i64 @"$sum"(i64 %"$number") {
  %"$total" = add i64 %"$number", -9223372036854775808
  ret i64 %"$total"
}

define i64 @"$difference"(i64 %"$first", i64 %"$second") {
  %"$d" = sub i64 %"$first", %"$second"
  ret i64 %"$d"
}

define i64 @"$seven"() {
  ret i64 7
}
