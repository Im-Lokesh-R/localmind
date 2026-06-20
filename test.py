def decode(shit,text):
    print(text)
    alphabet = "abcdefghijklmnopqrstuvwxyz"
    idx = [alphabet.index(c.lower()) for c in text]
    answer = "".join([alphabet[shit+n] for n in idx])
    return  answer



print(decode(-10,"DRSCSCDBEO"))
