class A:
    li = 'abc'
    def __init__(self, a: int):
        self.a = a
        self.l = [1, 2, 3]
    
a = A(0)
b = A(0)
b.li += 'd'

print(a.li)
print(b.l)