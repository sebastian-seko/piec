import math

one = open("/data/message.txt", "r")
str1 = one.read()
str1 = str1.split(",")
str1_raw = str1
two = open("/data/message2.txt", "r")
str2 = two.read()
str2 = str2.split(",")
strt = ([i == j for i, j in zip (str1,str2)])
#any( [i != j for i,j in zip (str1,str2)])
final = []
finalDEC = []
for i in range(len(strt)):
	if strt[i]:
		#print ("tru")
		#print (str1[i])
		final.append(str1[i])
		#finalDEC.append(int(str1[i], 16))
	else:
		#print ("else")
		#print (str1[i])
		#print (" ----> ")
		#print (str2[i])
		final.append(str2[i]+"->"+str1[i])
rowsize=12
for row in range(math.ceil(len(final)/rowsize)):
	#print (final[row])
	od = row*rowsize
	do = od+rowsize if len(final) >= od+rowsize else len(final)
	print(f"{od:03d}-{do-1:03d} \t{' '.join(final[od:do])}", end='')
	print('   ' * ((od+rowsize)-do), end='')
	print(f" \t")
