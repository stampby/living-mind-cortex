import cortex.thermorphic as t

# Generate atoms
a = t.encode_atom("hello", 256)
b = t.encode_atom("world", 256)

# Verify ranges
def check_range(val):
    return -1 <= val <= 1

# Similarity between different atoms should be near 0
print("Sim(a,b):", t._hrr_dot(a, b))
print("Sim(a,a):", t._hrr_dot(a, a))

# Test binding
c = t._hrr_bind(a, b)
print("Sim(c,a):", t._hrr_dot(c, a))
print("Sim(c,b):", t._hrr_dot(c, b))

# Range confirmation
assert check_range(t._hrr_dot(a, b))
assert check_range(t._hrr_dot(a, a))
assert check_range(t._hrr_dot(c, a))

print("ALL PHASE MATH CONSTRAINTS GREEN")
