use master;
drop database stocksearcher;
create database stocksearcher; 
use stocksearcher

drop table stocktype;
CREATE table stocktype (
	stockcode int primary key identity(1,1),
	stocktype nvarchar(100),
	isuse bit default 1
);

drop table type33;
create table type33 (
	type33code nvarchar(10) primary key,
	type33name nvarchar(100),
	isuse bit default 1
);

drop table type17;
create table type17 (
	type17code nvarchar(10) primary key,
	type17name nvarchar(100),
	isuse bit default 1
);

drop table typescale;
create table typescale(
	typescalecode nvarchar(10) primary key,
	typescalename nvarchar(100),
	isuse bit default 1
);

drop table stocklist;
create table stocklist(
	code nvarchar(10) Primary key,
	date nvarchar(8),
	name nvarchar(100),
	stockcode int foreign key references stocktype(stockcode),
	type33code nvarchar(10) foreign key references type33(type33code),
	type17code nvarchar(10) foreign key references type17(type17code),
	typescalecode nvarchar(10) foreign key references typescale(typescalecode),
	isuse bit default 1
);

drop table stockdata;
create table stockdata(
	code nvarchar (10) foreign key references stocklist(code),
	timestamp bigint,
	date date,
	open_price bigint,
	high_price bigint,
	low_price bigint,
	closed_price bigint,
	volume_price bigint,
	isuse bit default 1,
	primary key(code,timestamp),
);

drop table error;
create table error(
	idx bigint primary key identity(1,1),
	code nvarchar(10),
	occured_date date,
	error_message nvarchar(3000)
);

drop table normalMoveAvg;
create table normalMoveAvg(
	code nvarchar (10) foreign key references stocklist(code),
	date date,
	MvAvg5 bigint,
	MvAvg20 bigint,
	MvAvg60 bigint,
	MvAvg120 bigint,
	MvAvg240 bigint,
	volume_price bigint,
	isuse bit default 1,
	primary key(code,date)
);

drop table fibonachiMoveAvg;
create table fibonachiMoveAvg(
	code nvarchar (10) foreign key references stocklist(code),
	date date,
	MvAvg5 bigint,
	MvAvg8 bigint,
	MvAvg13 bigint,
	MvAvg21 bigint,
	MvAvg34 bigint,
	MvAvg55 bigint,
	MvAvg89 bigint,
	MvAvg144 bigint,
	MvAvg233 bigint,
	volume_price bigint,
	isuse bit default 1,
	primary key(code,date)
);

drop table bollingerbandMoveAvg;
create table bollingerbandMoveAvg(
	code nvarchar (10) foreign key references stocklist(code),
	date date,
	upperline bigint,
	lowerline bigint,
	MvAvg60 bigint,
	StDv bigint,
	volume_price bigint,
	isuse bit default 1,
	primary key(code,date)
);





















