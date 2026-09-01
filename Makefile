.PHONY: test

SERVICES := cdo_room_booking_api cfso_student_locker_api gs_rpg_leave_api sao_job_board_api cfso_cmms_api

test:
	@set -e; for service in $(SERVICES); do \
		echo "Testing $$service"; \
		(cd $$service && python3 -m unittest discover -s tests); \
	done
