-- A sample Lean 4 file with intentional sorry taint for testing sorryaudit

-- Fully trusted: proves by computation
theorem add_comm_zero (n : Nat) : n + 0 = n := by
  simp

-- Trusted: omega handles linear arithmetic cleanly
theorem nat_add_assoc (a b c : Nat) : (a + b) + c = a + (b + c) := by
  omega

-- TAINTED: uses sorry directly
theorem evil_theorem (n : Nat) : n = n + 1 := by
  sorry

-- TAINTED: uses admit
theorem also_evil (p q : Prop) : p → q := by
  admit

-- Depends on evil_theorem — transitively tainted
theorem derived_from_evil (n : Nat) : n + 1 = n + 2 := by
  have h := evil_theorem n
  sorry

-- Uses native_decide — bypasses kernel
theorem native_check : 2 + 2 = 4 := by
  native_decide
